"""Serialized, bounded TCP operations for Aquarius Plant LED.

Each operation owns a fresh connection. Startup and reconnection only read;
there is no background writer, retry queue, state restore or schedule replay.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from .protocol import (
    CHANNEL_QUERY,
    KNOWN_MODES,
    MODE_MANUAL,
    SYSTEM_QUERY,
    ProtocolError,
    StreamDecoder,
    SystemReply,
    channel_write_frame,
    mode_frame,
    parse_channels,
    parse_system,
    validate_percentage,
)

MAX_RECEIVED_BYTES = 8192
MANUAL_SAVE_DELAY = 0.1
SYSTEM_CHANNEL_DELAY = 0.2


class AquariusError(Exception):
    """An operation failed; no automatic command retry will occur."""


class ConflictError(AquariusError):
    """Status changed unexpectedly; stop instead of overriding another controller."""


class UnsupportedDeviceError(AquariusError):
    """The observed device profile or current mode has not been validated for writes."""


class RefreshRequiredError(AquariusError):
    """Read current device state before a new explicit command can be attempted."""


@dataclass(frozen=True)
class DeviceState:
    """A fresh system response and six logical A-F channel percentages."""

    system: SystemReply
    channels: tuple[int, ...]


class AquariusClient:
    """One client per device; serialize complete refresh/read-modify-write cycles.

    ``refresh`` must succeed before the first write and after any uncertain
    result. Setters accept an optional observed state to detect stale UI actions.
    Channel indices are zero-based; values are exact integer percentages.
    """

    def __init__(self, host: str, port: int = 8080, *, timeout: float = 5.0) -> None:
        if not isinstance(host, str) or not host.strip():
            raise ValueError("host is required")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be an integer in 1..65535")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be positive")
        self.host = host
        self.port = port
        self.timeout = float(timeout)
        self._lock = asyncio.Lock()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._active_task: Optional[asyncio.Task] = None
        self._decoder = StreamDecoder()
        self._received = 0
        self._closed = False
        self._needs_refresh = True
        self._epoch = 0
        self._last_state: Optional[DeviceState] = None

    @property
    def last_state(self) -> Optional[DeviceState]:
        """Last confirmed state, or None after any uncertain/failed operation."""
        return self._last_state

    async def refresh(self) -> DeviceState:
        """Read system/channel state without any mode, channel or clock writes."""
        return await self._execute(self._read_state, write=False)

    async def set_channel(
        self, index: int, value: int, expected_state: Optional[DeviceState] = None
    ) -> DeviceState:
        """Change one channel, preserve the other five, then explicitly save Manual."""
        if type(index) is not int or not 0 <= index < 6:
            raise ProtocolError("channel index must be an integer in 0..5")
        validate_percentage(value)

        async def operation() -> DeviceState:
            before = await self._prepare_write(expected_state)
            values = list(before.channels)
            values[index] = value
            desired = tuple(values)
            await self._send(channel_write_frame(desired, swap_cd=before.system.swap_cd))
            await asyncio.sleep(MANUAL_SAVE_DELAY)
            await self._send(mode_frame(MODE_MANUAL))
            after = await self._readback()
            self._verify_profile(before, after)
            if after.system.mode_raw != MODE_MANUAL or after.channels != desired:
                raise ConflictError("channel or mode readback differed; no restore was attempted")
            return after

        return await self._execute(operation, write=True)

    async def set_mode(
        self, mode: int, expected_state: Optional[DeviceState] = None
    ) -> DeviceState:
        """Choose an explicit mode without changing the stored channel/program data."""
        command = mode_frame(mode)

        async def operation() -> DeviceState:
            before = await self._prepare_write(expected_state)
            await self._send(command)
            after = await self._readback()
            self._verify_profile(before, after)
            if after.system.mode_raw != mode:
                raise ConflictError("mode readback differed; no restore was attempted")
            # Automatic/Shutdown can legitimately change output percentages.
            if mode == MODE_MANUAL and after.channels != before.channels:
                raise ConflictError("channels changed unexpectedly while selecting Manual")
            return after

        return await self._execute(operation, write=True)

    async def close(self) -> None:
        """Permanently close and cancel an active transaction without compensating writes."""
        self._closed = True
        self._needs_refresh = True
        self._last_state = None
        self._epoch += 1
        task = self._active_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        await self._disconnect()
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)

    async def _execute(
        self, operation: Callable[[], Awaitable[DeviceState]], *, write: bool
    ) -> DeviceState:
        epoch = self._epoch
        async with self._lock:
            if self._closed:
                raise AquariusError("client is closed")
            if write and (self._needs_refresh or epoch != self._epoch):
                raise RefreshRequiredError("refresh required before a new explicit command")
            self._active_task = asyncio.current_task()
            try:
                state = await asyncio.wait_for(
                    self._connected_operation(operation),
                    timeout=self.timeout * 8 + MANUAL_SAVE_DELAY,
                )
            except asyncio.CancelledError:
                self._invalidate()
                raise
            except (AquariusError, ProtocolError):
                self._invalidate()
                raise
            except (OSError, asyncio.TimeoutError, EOFError):
                self._invalidate()
                # No endpoint, raw reply, credentials or low-level error body in exceptions.
                raise AquariusError(
                    "device communication failed; refresh before another command"
                ) from None
            finally:
                try:
                    await self._disconnect()
                except asyncio.CancelledError:
                    self._invalidate()
                    raise
                finally:
                    self._active_task = None
            self._last_state = state
            self._needs_refresh = False
            return state

    async def _connected_operation(
        self, operation: Callable[[], Awaitable[DeviceState]]
    ) -> DeviceState:
        self._received = 0
        await self._connect()
        return await operation()

    async def _connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, limit=4096), self.timeout
        )
        self._decoder = StreamDecoder()

    async def _readback(self) -> DeviceState:
        # This controller family can answer a read with E2 FA, the same opcode
        # as a channel write. Never accept the write socket's echo as readback.
        await self._disconnect()
        await self._connect()
        return await self._read_state()

    async def _prepare_write(self, expected_state: Optional[DeviceState]) -> DeviceState:
        previous = expected_state if expected_state is not None else self._last_state
        before = await self._read_state()
        if previous is None or before != previous:
            raise ConflictError("device state changed before command; refresh and review it")
        if not before.system.write_supported or before.system.mode_raw not in KNOWN_MODES:
            raise UnsupportedDeviceError("device profile or current mode is unverified for writes")
        return before

    @staticmethod
    def _verify_profile(before: DeviceState, after: DeviceState) -> None:
        a, b = before.system, after.system
        if (
            a.version_bytes != b.version_bytes
            or a.controller_bytes != b.controller_bytes
            or a.channel_count_raw != b.channel_count_raw
        ):
            raise ConflictError("device profile changed during command")

    def _invalidate(self) -> None:
        self._last_state = None
        self._needs_refresh = True
        self._epoch += 1

    async def _disconnect(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), min(self.timeout, 1.0))
            except (OSError, asyncio.TimeoutError):
                pass

    async def _send(self, frame: bytes) -> None:
        if self._writer is None or self._closed:
            raise AquariusError("connection is not available")
        self._writer.write(frame)
        await asyncio.wait_for(self._writer.drain(), self.timeout)

    async def _read_state(self) -> DeviceState:
        system = parse_system(await self._query(SYSTEM_QUERY))
        await self._wait_before_channel_query()
        raw_channels = await self._query(CHANNEL_QUERY)
        channels = parse_channels(raw_channels, swap_cd=system.swap_cd)
        return DeviceState(system, channels)

    async def _wait_before_channel_query(self) -> None:
        """Pause between queries and reject status sent before it was requested.

        Merely clearing the decoder would miss data already waiting in the
        stream reader. Consume the entire pause, accepting only acknowledgement
        candidates or complete extended messages, then require a clean boundary.
        """
        deadline = asyncio.get_running_loop().time() + SYSTEM_CHANNEL_DELAY
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            if self._reader is None:
                raise AquariusError("connection is not available")
            try:
                data = await asyncio.wait_for(self._reader.read(1024), remaining)
            except asyncio.TimeoutError:
                break
            for message in self._decode(data):
                if message.kind == "primary":
                    raise ProtocolError("unsolicited status before the channel query")
        if self._decoder.buffered_bytes:
            raise ProtocolError("unfinished unsolicited frame before the channel query")

    async def _query(self, query: bytes) -> bytes:
        await self._send(query)
        return await asyncio.wait_for(self._read_reply(query), self.timeout)

    async def _read_reply(self, query: bytes) -> bytes:
        while True:
            if self._reader is None:
                raise AquariusError("connection is not available")
            data = await self._reader.read(1024)
            messages = self._decode(data)
            for message in messages:
                if message.kind != "primary" or message.raw[1] != query[1]:
                    continue
                operations = (0xFC, 0xFA) if query == CHANNEL_QUERY else (0xFC,)
                if message.raw[2] not in operations:
                    continue
                if message.raw == query:
                    # E2 FC followed by only zero padding is indistinguishable
                    # from a query echo. Refuse the ambiguity: false zeroes
                    # could erase the other five channels during a later write.
                    # The verified controller reports all-off as E2 FA.
                    raise ProtocolError("query echo is not a verified device reply")
                if (
                    self._decoder.buffered_bytes
                    or sum(item.kind == "primary" for item in messages) != 1
                ):
                    raise ProtocolError("unsolicited extra or partial status beside the reply")
                return message.raw

    def _decode(self, data: bytes):
        if not data:
            raise AquariusError("connection closed before a valid reply")
        self._received += len(data)
        if self._received > MAX_RECEIVED_BYTES:
            raise ProtocolError("transaction receive limit exceeded")
        return self._decoder.feed(data)

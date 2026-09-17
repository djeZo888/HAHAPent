"""Serialized, bounded TCP operations for Aquarius Plant LED.

Each operation owns a fresh connection. Startup and reconnection only read;
there is no background writer, retry queue, state restore or schedule replay.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from .compact import (
    mix_rgb,
    peak_intensity,
    scale_channels,
    validate_intensity,
    validate_rgb,
    validate_roles,
)
from .protocol import (
    CHANNEL_QUERY,
    MODE_AUTOMATIC,
    MODE_MANUAL,
    MODE_SHUTDOWN,
    SUPPORTED_CONTROL_MODES,
    SYSTEM_QUERY,
    ProtocolError,
    StreamDecoder,
    SystemReply,
    channel_write_frame,
    mode_frame,
    parse_channels,
    parse_system,
    permute_channels,
    validate_percentage,
)

MAX_RECEIVED_BYTES = 8192
MANUAL_SAVE_DELAY = 0.1
SYSTEM_CHANNEL_DELAY = 0.2
WRITE_DRAIN_PAUSE = 0.2


class AquariusError(Exception):
    """An operation failed; no automatic command retry will occur."""


class ConflictError(AquariusError):
    """Status changed unexpectedly; stop instead of overriding another controller."""


class UnsupportedDeviceError(AquariusError):
    """The observed device profile or current mode has not been validated for writes."""


class RefreshRequiredError(AquariusError):
    """Read current device state before a new explicit command can be attempted."""


class CompactInputError(ProtocolError):
    """A fresh read found no safe basis for the requested compact output."""

    def __init__(self, message: str, state: DeviceState) -> None:
        super().__init__(message)
        self.state = state


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
        self._operation_epoch: Optional[int] = None
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
            channel_command = channel_write_frame(desired, swap_cd=before.system.swap_cd)
            manual_command = mode_frame(MODE_MANUAL)
            await self._send(channel_command)
            await self._quarantine(MANUAL_SAVE_DELAY, (channel_command,))
            await self._send(manual_command)
            after = await self._readback(before, MODE_MANUAL, (channel_command, manual_command))
            self._verify_profile(before, after)
            if after.system.mode_raw != MODE_MANUAL or after.channels != desired:
                raise ConflictError("channel or mode readback differed; no restore was attempted")
            return after

        return await self._execute(operation, write=True)

    async def set_mode(
        self, mode: int, expected_state: Optional[DeviceState] = None
    ) -> DeviceState:
        """Choose an explicit mode without changing the stored channel/program data."""
        if type(mode) is not int or mode not in SUPPORTED_CONTROL_MODES:
            raise ProtocolError("only Automatic or Manual control has been validated")
        command = mode_frame(mode)

        async def operation() -> DeviceState:
            before = await self._prepare_write(expected_state)
            await self._send(command)
            after = await self._readback(before, mode, (command,))
            self._verify_profile(before, after)
            if after.system.mode_raw != mode:
                raise ConflictError("mode readback differed; no restore was attempted")
            # Automatic can legitimately change output percentages.
            if mode == MODE_MANUAL and after.channels != before.channels:
                raise ConflictError("channels changed unexpectedly while selecting Manual")
            return after

        return await self._execute(operation, write=True)

    async def set_compact(
        self,
        *,
        rgb_color=None,
        intensity=None,
        channel_roles,
        manual_channels=None,
        expected_state: Optional[DeviceState] = None,
    ) -> DeviceState:
        """Apply one explicit manual recipe, never an inferred power restoration.

        Brightness-only changes scale the complete freshly observed spectrum.
        The optional Off basis comes only from the coordinator's trusted power
        memory; it is never treated as a new saved origin or replayed implicitly.
        """
        try:
            roles = validate_roles(channel_roles)
            rgb = None if rgb_color is None else validate_rgb(rgb_color)
            level = None if intensity is None else validate_intensity(intensity)
        except ValueError as error:
            raise ProtocolError(str(error)) from None
        if rgb is None and level is None:
            raise ProtocolError("A colour or intensity is required")
        if level == 0 or rgb == (0, 0, 0):
            raise ProtocolError("Zero compact output requires the explicit power Off action")
        if manual_channels is not None:
            manual_channels = permute_channels(manual_channels)
            if not any(manual_channels):
                raise ProtocolError("The supplied Manual basis must be nonzero")

        async def operation() -> DeviceState:
            # Only Shutdown needs the separate power gate. Ordinary manual
            # recipes retain the already validated channel-control profile gate.
            previous = expected_state if expected_state is not None else self._last_state
            waking = previous is not None and previous.system.mode_raw == MODE_SHUTDOWN
            before = await self._prepare_write(expected_state, power=waking)
            basis = manual_channels if waking else before.channels
            if rgb is None:
                if basis is None or not any(basis):
                    raise CompactInputError(
                        "Choose a colour first: no nonzero Manual mix is known", before
                    )
                desired = scale_channels(basis, level)
            else:
                chosen_level = level
                if chosen_level is None:
                    # Retained Shutdown bytes do not describe visible output or
                    # a trusted prior choice. Only saved Manual origin may
                    # supply its level; otherwise colour starts modestly.
                    chosen_level = peak_intensity(basis) if basis is not None else 0
                    chosen_level = chosen_level or 5
                desired = mix_rgb(rgb, chosen_level, roles)
            desired = permute_channels(desired)

            if waking:
                # Wake into a confirmed unchanged exposed vector, then guard
                # again before applying this new user-selected target. Calling
                # ordinary On here could briefly restore/resume a different mix.
                manual = mode_frame(MODE_MANUAL)
                await self._send(manual)
                awake = await self._readback(before, MODE_MANUAL, (manual,))
                self._verify_profile(before, awake)
                if awake.system.mode_raw != MODE_MANUAL or awake.channels != before.channels:
                    raise ConflictError("Manual wake contradicted the observed Off state")
                await self._disconnect()
                await self._connect()
                before = await self._prepare_write(awake)

            command = channel_write_frame(desired, swap_cd=before.system.swap_cd)
            manual = mode_frame(MODE_MANUAL)
            await self._send(command)
            await self._quarantine(MANUAL_SAVE_DELAY, (command,))
            await self._send(manual)
            after = await self._readback(before, MODE_MANUAL, (command, manual))
            self._verify_profile(before, after)
            if after.system.mode_raw != MODE_MANUAL or after.channels != desired:
                raise ConflictError("compact output was not independently confirmed")
            return after

        return await self._execute(operation, write=True)

    async def turn_off(self, expected_state: Optional[DeviceState] = None) -> DeviceState:
        """Explicit software Shutdown, separately gated and independently confirmed."""

        async def operation() -> DeviceState:
            before = await self._prepare_write(expected_state, power=True)
            if before.system.mode_raw == MODE_SHUTDOWN:
                return before
            command = mode_frame(MODE_SHUTDOWN)
            await self._send(command)
            after = await self._readback(before, MODE_SHUTDOWN, (command,))
            self._verify_profile(before, after)
            if after.system.mode_raw != MODE_SHUTDOWN or after.channels not in (
                before.channels,
                (0,) * 6,
            ):
                raise ConflictError("software Off readback was not the expected state")
            return after

        return await self._execute(operation, write=True)

    async def turn_on(
        self,
        manual_channels: Optional[tuple[int, ...]] = None,
        expected_state: Optional[DeviceState] = None,
    ) -> DeviceState:
        """Explicit On: restore a supplied remembered Manual mix or resume Automatic."""
        if manual_channels is not None:
            manual_channels = permute_channels(manual_channels)
            if not any(manual_channels):
                raise ProtocolError("Manual power restoration requires a nonzero saved mix")

        async def operation() -> DeviceState:
            before = await self._prepare_write(expected_state, power=True)
            if before.system.mode_raw != MODE_SHUTDOWN:
                return before
            if manual_channels is None:
                command = mode_frame(MODE_AUTOMATIC)
                await self._send(command)
                after = await self._readback(before, MODE_AUTOMATIC, (command,))
                self._verify_profile(before, after)
                if after.system.mode_raw != MODE_AUTOMATIC:
                    raise ConflictError("Automatic power restoration was not confirmed")
                return after
            manual = mode_frame(MODE_MANUAL)
            await self._send(manual)
            awake = await self._readback(before, MODE_MANUAL, (manual,))
            self._verify_profile(before, awake)
            if awake.system.mode_raw != MODE_MANUAL:
                raise ConflictError("Manual power restoration was not confirmed")
            if awake.channels == manual_channels:
                return awake
            # Never write a channel vector while Shutdown is active. Only the
            # observed zero-Off -> independently confirmed zero-Manual path may
            # need the remembered mix restored after the explicit mode command.
            if before.channels != (0,) * 6 or awake.channels != (0,) * 6:
                raise ConflictError("Manual return contradicted the observed Off output")
            await self._disconnect()
            await self._connect()
            guarded = await self._prepare_write(awake)
            command = channel_write_frame(manual_channels, swap_cd=guarded.system.swap_cd)
            await self._send(command)
            await self._quarantine(MANUAL_SAVE_DELAY, (command,))
            await self._send(manual)
            after = await self._readback(guarded, MODE_MANUAL, (command, manual))
            self._verify_profile(guarded, after)
            if after.system.mode_raw != MODE_MANUAL or after.channels != manual_channels:
                raise ConflictError("saved Manual mix was not independently confirmed")
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
            self._operation_epoch = self._epoch
            operation_task = asyncio.create_task(self._connected_operation(operation))
            # A cancelled Python 3.14 shield reports exceptions from its inner
            # task to the loop, even when another waiter retrieves them later.
            # Shield a non-raising result envelope instead, then unwrap it.
            operation_result = asyncio.gather(operation_task, return_exceptions=True)
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(operation_result),
                    timeout=self.timeout * 8 + MANUAL_SAVE_DELAY,
                )
                if isinstance(result[0], BaseException):
                    raise result[0]
                state = result[0]
            except asyncio.CancelledError:
                self._invalidate()
                raise
            except CompactInputError as error:
                # This error is emitted only after a complete fresh read and
                # before any output command. Revoke older queued requests but
                # retain that confirmed observation for a new explicit choice.
                self._epoch += 1
                self._last_state = error.state
                self._needs_refresh = False
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
                    # Invalidate above before cancellation reaches nested I/O:
                    # Python 3.9 wait_for can swallow cancellation when its
                    # inner awaitable completes concurrently. A revoked epoch
                    # still prevents the next send in that operation.
                    if not operation_task.done():
                        operation_task.cancel()
                    cancelled = await self._settle_operation(operation_task)
                    await self._disconnect()
                    if cancelled:
                        raise asyncio.CancelledError
                except asyncio.CancelledError:
                    self._invalidate()
                    raise
                finally:
                    self._active_task = None
                    self._operation_epoch = None
            self._last_state = state
            self._needs_refresh = False
            return state

    async def _settle_operation(self, task: asyncio.Task) -> bool:
        """Do not release the transaction lock while cancelled I/O can continue."""
        settled = asyncio.gather(task, return_exceptions=True)
        cancelled = False
        while not settled.done():
            try:
                await asyncio.shield(settled)
            except asyncio.CancelledError:
                cancelled = True
                self._invalidate()
                task.cancel()
        return cancelled

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

    async def _readback(
        self, before: DeviceState, expected_mode: int, commands: tuple[bytes, ...]
    ) -> DeviceState:
        # drain() confirms transport-buffer acceptance, not device processing.
        # Keep the write connection open until a queried system reply confirms
        # the requested mode and unchanged profile. Exact echoes of the writes
        # and ACK candidates are consumed but never counted as confirmation.
        await self._quarantine(WRITE_DRAIN_PAUSE, commands)
        system = parse_system(await self._query(SYSTEM_QUERY, ignored_primary=commands))
        self._verify_system_profile(before.system, system)
        if system.mode_raw != expected_mode:
            raise ConflictError("queried mode did not confirm the command before disconnect")
        # This controller family can answer a read with E2 FA, the same opcode
        # as a channel write. Never accept the write socket's echo as readback.
        await self._disconnect()
        await self._connect()
        return await self._read_state()

    async def _prepare_write(
        self, expected_state: Optional[DeviceState], *, power: bool = False
    ) -> DeviceState:
        previous = expected_state if expected_state is not None else self._last_state
        before = await self._read_state()
        if previous is None or before.system != previous.system:
            raise ConflictError("device state changed before command; refresh and review it")
        # An explicit user action may interrupt a running program. Its levels
        # can legitimately change since HA's last poll: preserve the other five
        # from this fresh read, never from the older observed vector. A changed
        # mode/profile or changed Manual output still indicates a conflict.
        if before.system.mode_raw != MODE_AUTOMATIC and before.channels != previous.channels:
            raise ConflictError("device state changed before command; refresh and review it")
        allowed_modes = (
            SUPPORTED_CONTROL_MODES | {MODE_SHUTDOWN} if power else SUPPORTED_CONTROL_MODES
        )
        if not before.system.write_supported or before.system.mode_raw not in allowed_modes:
            raise UnsupportedDeviceError("device profile or current mode is unverified for writes")
        if power and not before.system.power_supported:
            raise UnsupportedDeviceError("software power control is unverified for this profile")
        return before

    @staticmethod
    def _verify_profile(before: DeviceState, after: DeviceState) -> None:
        AquariusClient._verify_system_profile(before.system, after.system)

    @staticmethod
    def _verify_system_profile(a: SystemReply, b: SystemReply) -> None:
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
        if self._operation_epoch is not None and self._operation_epoch != self._epoch:
            raise RefreshRequiredError("cancelled transaction cannot send further commands")
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
        """Pause between queries and reject status sent before it was requested."""
        await self._quarantine(SYSTEM_CHANNEL_DELAY)

    async def _quarantine(self, duration: float, echoes: tuple[bytes, ...] = ()) -> None:
        """Consume a receive boundary interval without mistaking echoes for status.

        Merely clearing the decoder would miss data already waiting in the
        stream reader. Consume the entire pause, accepting only acknowledgement
        candidates or complete extended messages, then require a clean boundary.
        """
        deadline = asyncio.get_running_loop().time() + duration
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
                if message.kind == "primary" and message.raw not in echoes:
                    raise ProtocolError("unsolicited status before the next query")
        if self._decoder.buffered_bytes:
            raise ProtocolError("unfinished unsolicited frame before the next query")

    async def _query(self, query: bytes, *, ignored_primary: tuple[bytes, ...] = ()) -> bytes:
        await self._send(query)
        return await asyncio.wait_for(self._read_reply(query, ignored_primary), self.timeout)

    async def _read_reply(self, query: bytes, ignored_primary: tuple[bytes, ...] = ()) -> bytes:
        while True:
            if self._reader is None:
                raise AquariusError("connection is not available")
            data = await self._reader.read(1024)
            messages = [
                message
                for message in self._decode(data)
                if message.kind != "primary" or message.raw not in ignored_primary
            ]
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

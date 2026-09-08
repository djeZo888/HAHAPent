"""Bounded AMled framing and six-channel percentage values.

This module is pure Python and performs no I/O. Raw controller/version fields
are protocol observations, not a hardware identifier or a firmware name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MODE_AUTOMATIC = 0
MODE_MANUAL = 1
MODE_SHUTDOWN = 8
KNOWN_MODES = frozenset((MODE_AUTOMATIC, MODE_MANUAL, MODE_SHUTDOWN))
SWAPPED_CONTROLLER = (0x14, 0x32)

# A release must list only profiles validated through device readback. An
# unrecognized controller can be inspected but never receives write commands.
VERIFIED_WRITE_PROFILES: frozenset[tuple[tuple[int, int], tuple[int, int], int]] = frozenset()


class ProtocolError(ValueError):
    """A frame or value is malformed or outside the supported protocol."""


def frame_payload(payload: bytes) -> bytes:
    """Build a fixed-size core frame; longer command families are unsupported."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if len(payload) > 18:
        raise ProtocolError("core payload exceeds 18 bytes")
    return b"\xf1" + payload.ljust(18, b"\0") + b"\xf3"


SYSTEM_QUERY = frame_payload(b"\xe1\xfc")
CHANNEL_QUERY = frame_payload(b"\xe2\xfc")


def validate_percentage(value: int) -> int:
    """Reject floats, booleans and out-of-range percentages without coercion."""
    if type(value) is not int or not 0 <= value <= 100:
        raise ProtocolError("channel percentage must be an integer in 0..100")
    return value


def permute_channels(values: Iterable[int], *, swap_cd: bool = False) -> tuple[int, ...]:
    """Map wire/logical order; only the documented C/D swap is supported."""
    result = tuple(values)
    if len(result) != 6:
        raise ProtocolError("exactly six channel percentages are required")
    for value in result:
        validate_percentage(value)
    a, b, c, d, e, f = result
    return (a, b, d, c, e, f) if swap_cd else result


def channel_write_frame(values: Iterable[int], *, swap_cd: bool = False) -> bytes:
    """Encode all six fresh logical channel percentages."""
    return frame_payload(b"\xe2\xfa" + bytes(permute_channels(values, swap_cd=swap_cd)))


def mode_frame(mode: int) -> bytes:
    """Encode one explicit mode choice; Automatic means the stored program."""
    if type(mode) is not int or mode not in KNOWN_MODES:
        raise ProtocolError("unsupported mode; expected automatic=0, manual=1 or shutdown=8")
    return frame_payload(bytes((0xE1, 0xFA, 0xDB, mode)))


def _validate_primary(frame: bytes, command: int, operations: tuple[int, ...]) -> None:
    if not isinstance(frame, bytes):
        raise TypeError("frame must be bytes")
    if len(frame) != 20 or frame[0] != 0xF1 or frame[-1] != 0xF3:
        raise ProtocolError("expected a complete 20-byte core frame")
    if frame[1] != command or frame[2] not in operations:
        raise ProtocolError("unexpected reply command or operation")


@dataclass(frozen=True)
class SystemReply:
    """System observations, including modes the integration does not recognize."""

    mode_raw: int
    version_bytes: tuple[int, int]
    controller_bytes: tuple[int, int]
    channel_count_raw: int
    app_ui_channel_count: int
    swap_cd: bool

    @property
    def write_supported(self) -> bool:
        """Whether this exact observed profile has been validated for writes."""
        return (
            self.controller_bytes,
            self.version_bytes,
            self.channel_count_raw,
        ) in VERIFIED_WRITE_PROFILES


def parse_system(frame: bytes) -> SystemReply:
    _validate_primary(frame, 0xE1, (0xFC,))
    if frame == SYSTEM_QUERY:
        raise ProtocolError("system query echo is not device status")
    controller = (frame[9], frame[10])
    return SystemReply(
        mode_raw=frame[4],
        version_bytes=(frame[7], frame[8]),
        controller_bytes=controller,
        channel_count_raw=frame[11],
        app_ui_channel_count=3 if frame[11] == 3 else 6,
        swap_cd=controller == SWAPPED_CONTROLLER,
    )


def parse_channels(frame: bytes, *, swap_cd: bool = False) -> tuple[int, ...]:
    _validate_primary(frame, 0xE2, (0xFC, 0xFA))
    return permute_channels(frame[3:9], swap_cd=swap_cd)


@dataclass(frozen=True)
class Message:
    """A complete frame or an untrusted one-byte acknowledgement candidate."""

    kind: str
    raw: bytes


class StreamDecoder:
    """Decode core and length-delimited extended frames without I/O or effects.

    Interior F1/F3/F5/F6 bytes are payload, not delimiters. Extended messages
    are consumed whole and must never masquerade as system/channel replies.
    F5/F6 outside a frame are merely candidates, never confirmation of a write.
    """

    def __init__(self, *, max_buffer: int = 4096) -> None:
        if type(max_buffer) is not int or max_buffer < 262:
            raise ValueError("max_buffer must hold a 262-byte extended frame")
        self.max_buffer = max_buffer
        self.discarded_bytes = 0
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[Message]:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if len(self._buffer) + len(data) > self.max_buffer:
            self._buffer.clear()
            raise ProtocolError("receive buffer limit exceeded")
        self._buffer.extend(data)
        messages = []
        while self._buffer:
            first = self._buffer[0]
            if first == 0xF1:
                if len(self._buffer) < 20:
                    break
                if self._buffer[19] == 0xF3:
                    messages.append(Message("primary", bytes(self._buffer[:20])))
                    del self._buffer[:20]
                    continue
            elif first == 0x01:
                header = b"\x01\xfe\x68"
                prefix_length = min(len(self._buffer), 3)
                if self._buffer[:prefix_length] == header[:prefix_length]:
                    if len(self._buffer) < 4:
                        break
                    length = 7 + self._buffer[3]
                    if len(self._buffer) < length:
                        break
                    if self._buffer[length - 3 : length] != b"\x67\xfd\x02":
                        self._buffer.clear()
                        raise ProtocolError("invalid extended-frame trailer")
                    messages.append(Message("extended", bytes(self._buffer[:length])))
                    del self._buffer[:length]
                    continue
            elif first in (0xF5, 0xF6):
                messages.append(Message("ack_candidate", bytes(self._buffer[:1])))
                del self._buffer[:1]
                continue
            del self._buffer[0]
            self.discarded_bytes += 1
        return messages

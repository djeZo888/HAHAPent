"""Synthetic framing, parser and percentage tests; no device captures."""

import unittest
from unittest.mock import patch

from tests.aquarius_tcp_helpers import (
    SYNTHETIC_PROFILES,
    channels_reply,
    extended_reply,
    protocol,
    system_reply,
)


class AquariusProtocolTests(unittest.TestCase):
    def test_read_query_golden_vectors(self):
        self.assertEqual(protocol.SYSTEM_QUERY, bytes.fromhex("f1 e1 fc " + "00 " * 16 + "f3"))
        self.assertEqual(protocol.CHANNEL_QUERY, bytes.fromhex("f1 e2 fc " + "00 " * 16 + "f3"))

    def test_supported_builder_is_fixed_length_and_rejects_long_families(self):
        for length in range(19):
            with self.subTest(length=length):
                payload = bytes(range(length))
                self.assertEqual(
                    protocol.frame_payload(payload),
                    b"\xf1" + payload + b"\0" * (18 - length) + b"\xf3",
                )
        with self.assertRaises(protocol.ProtocolError):
            protocol.frame_payload(b"x" * 19)
        with self.assertRaises(TypeError):
            protocol.frame_payload(bytearray())

    def test_channel_golden_vectors_and_swapping_are_symmetric(self):
        values = (0, 100, 30, 40, 50, 60)
        for swap, wire in ((False, values), (True, (0, 100, 40, 30, 50, 60))):
            with self.subTest(swap=swap):
                frame = protocol.channel_write_frame(values, swap_cd=swap)
                self.assertEqual(frame, b"\xf1\xe2\xfa" + bytes(wire) + b"\0" * 10 + b"\xf3")
                self.assertEqual(protocol.parse_channels(frame, swap_cd=swap), values)

    def test_channels_are_exact_six_integer_percentages(self):
        invalid = [(), (1,) * 5, (1,) * 7]
        invalid.extend((value, 0, 0, 0, 0, 0) for value in (-1, 101, 255, True, 1.0, "2", None))
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(protocol.ProtocolError):
                protocol.channel_write_frame(values)

    def test_raw_channel_scale_is_never_guessed_or_clamped(self):
        for value in (101, 127, 255):
            with self.subTest(value=value), self.assertRaises(protocol.ProtocolError):
                protocol.parse_channels(channels_reply((value, 0, 0, 0, 0, 0)))

    def test_mode_golden_vectors(self):
        for mode in (0, 1, 8):
            self.assertEqual(
                protocol.mode_frame(mode),
                b"\xf1\xe1\xfa\xdb" + bytes((mode,)) + b"\0" * 14 + b"\xf3",
            )
        for mode in (-1, 2, 16, 255, True, 1.0, None):
            with self.subTest(mode=mode), self.assertRaises(protocol.ProtocolError):
                protocol.mode_frame(mode)

    def test_system_fields_and_unknown_mode_are_preserved(self):
        for mode in (0, 1, 8, 16, 255):
            state = protocol.parse_system(system_reply(mode))
            self.assertEqual(state.mode_raw, mode)
            self.assertEqual(state.controller_bytes, (0x12, 0x3C))
            self.assertEqual(state.version_bytes, (2, 5))
            self.assertEqual(state.channel_count_raw, 6)
            self.assertEqual(state.app_ui_channel_count, 6)

    def test_swap_requires_both_exact_controller_markers(self):
        for controller, expected in (
            ((0x14, 0x32), True),
            ((0x14, 0x31), False),
            ((0x13, 0x32), False),
            ((0, 0), False),
            ((0x12, 0x3C), False),
        ):
            with self.subTest(controller=controller):
                self.assertEqual(
                    protocol.parse_system(system_reply(controller=controller)).swap_cd, expected
                )

    def test_three_channel_hint_does_not_allow_writes_by_default(self):
        with patch.object(protocol, "VERIFIED_WRITE_PROFILES", SYNTHETIC_PROFILES):
            system = protocol.parse_system(system_reply(count=3))
            self.assertEqual(system.app_ui_channel_count, 3)
            self.assertFalse(system.write_supported)

    def test_writes_require_exact_controller_version_and_count(self):
        with patch.object(protocol, "VERIFIED_WRITE_PROFILES", SYNTHETIC_PROFILES):
            self.assertTrue(protocol.parse_system(system_reply()).write_supported)
            for kwargs in ({"version": (2, 6)}, {"controller": (0x12, 0x3D)}, {"count": 7}):
                self.assertFalse(protocol.parse_system(system_reply(**kwargs)).write_supported)

    def test_release_enables_only_the_verified_profile_and_two_control_modes(self):
        self.assertEqual(protocol.VERIFIED_WRITE_PROFILES, frozenset({((28, 30), (26, 29), 6)}))
        self.assertEqual(protocol.SUPPORTED_CONTROL_MODES, frozenset({0, 1}))
        observed = {"controller": (28, 30), "version": (26, 29), "count": 6}
        self.assertTrue(protocol.parse_system(system_reply(**observed)).write_supported)
        for changed in (
            {"controller": (28, 31)},
            {"version": (26, 30)},
            {"count": 3},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(
                    protocol.parse_system(system_reply(**{**observed, **changed})).write_supported
                )
        self.assertFalse(protocol.parse_system(system_reply()).write_supported)

    def test_malformed_or_wrong_replies_are_rejected(self):
        valid = system_reply()
        for frame in (
            b"",
            valid[:-1],
            valid + b"\0",
            b"\0" + valid[1:],
            valid[:-1] + b"\0",
            protocol.CHANNEL_QUERY,
            protocol.mode_frame(1),
            protocol.SYSTEM_QUERY,
        ):
            with self.subTest(frame=frame), self.assertRaises(protocol.ProtocolError):
                protocol.parse_system(frame)
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_channels(channels_reply(operation=0xFD))

    def test_channel_reply_accepts_read_and_device_fa_response(self):
        for operation in (0xFC, 0xFA):
            self.assertEqual(
                protocol.parse_channels(channels_reply(operation=operation)),
                (10, 20, 30, 40, 50, 60),
            )

    def test_every_two_fragment_boundary_and_coalesced_replies(self):
        frames = [system_reply(), channels_reply(), system_reply(0)]
        raw = b"".join(frames)
        for split in range(len(raw) + 1):
            with self.subTest(split=split):
                decoder = protocol.StreamDecoder()
                result = decoder.feed(raw[:split]) + decoder.feed(raw[split:])
                self.assertEqual([message.raw for message in result], frames)
                self.assertEqual(decoder.buffered_bytes, 0)

    def test_bytewise_frame_and_embedded_markers(self):
        raw = bytearray(system_reply())
        raw[12:16] = b"\xf1\xf3\xf5\xf6"
        decoder = protocol.StreamDecoder()
        result = []
        for value in raw:
            result.extend(decoder.feed(bytes((value,))))
        self.assertEqual([message.raw for message in result], [bytes(raw)])

    def test_extended_frames_skip_embedded_primary_at_all_fragment_boundaries(self):
        extended = extended_reply(system_reply() + b"\xf5\xf6")
        raw = extended + channels_reply()
        for split in range(len(raw) + 1):
            with self.subTest(split=split):
                decoder = protocol.StreamDecoder()
                result = decoder.feed(raw[:split]) + decoder.feed(raw[split:])
                self.assertEqual([message.kind for message in result], ["extended", "primary"])
                self.assertEqual([message.raw for message in result], [extended, channels_reply()])

    def test_extended_empty_and_max_payload(self):
        for payload in (b"", b"\xf1" * 255):
            raw = extended_reply(payload)
            result = protocol.StreamDecoder(max_buffer=262).feed(raw)
            self.assertEqual([message.raw for message in result], [raw])
            self.assertEqual(result[0].kind, "extended")

    def test_invalid_extended_trailer_cannot_expose_embedded_primary(self):
        raw = extended_reply(system_reply())[:-1] + b"\0"
        decoder = protocol.StreamDecoder()
        with self.assertRaises(protocol.ProtocolError):
            decoder.feed(raw)
        self.assertEqual(decoder.buffered_bytes, 0)

    def test_acknowledgements_are_only_candidates(self):
        result = protocol.StreamDecoder().feed(b"\xf5" + system_reply() + b"\xf6")
        self.assertEqual(
            [message.kind for message in result], ["ack_candidate", "primary", "ack_candidate"]
        )

    def test_corrupt_primary_and_noise_recovery(self):
        decoder = protocol.StreamDecoder()
        corrupt = system_reply()[:-1] + b"\0"
        result = decoder.feed(b"garbage" + corrupt + system_reply())
        self.assertEqual([message.raw for message in result], [system_reply()])
        self.assertGreater(decoder.discarded_bytes, 0)

    def test_decoder_input_and_buffer_are_bounded(self):
        for size in (0, 261, True, 4096.0):
            with self.assertRaises(ValueError):
                protocol.StreamDecoder(max_buffer=size)
        decoder = protocol.StreamDecoder(max_buffer=262)
        with self.assertRaises(protocol.ProtocolError):
            decoder.feed(b"x" * 263)
        self.assertEqual(decoder.buffered_bytes, 0)
        with self.assertRaises(TypeError):
            decoder.feed(bytearray())


if __name__ == "__main__":
    unittest.main()

"""Fault-injected synthetic TCP tests; no actual lamp validation is implied."""

import asyncio
import unittest
from unittest.mock import patch

from tests.aquarius_tcp_helpers import (
    SYNTHETIC_PROFILES,
    SyntheticLamp,
    channels_reply,
    client,
    extended_reply,
    protocol,
    system_reply,
)


class AquariusClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lamp = SyntheticLamp()
        port = await self.lamp.start()
        self.client = client.AquariusClient("127.0.0.1", port, timeout=0.4)
        self.profiles = patch.object(protocol, "VERIFIED_WRITE_PROFILES", SYNTHETIC_PROFILES)
        self.profiles.start()

    async def asyncTearDown(self):
        await self.client.close()
        await self.lamp.close()
        self.profiles.stop()

    async def test_startup_poll_and_reconnect_only_send_two_reads(self):
        for _ in range(3):
            state = await self.client.refresh()
            self.assertEqual(state.channels, (10, 20, 30, 40, 50, 60))
            self.assertEqual(state.system.mode_raw, 1)
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY, protocol.CHANNEL_QUERY] * 3)
        self.assertEqual(self.lamp.connections, 3)
        self.assertEqual(self.lamp.writes, [])

    async def test_fragmented_fa_read_response_skips_ack_and_extended_frames(self):
        self.lamp.channel_operation = 0xFA
        self.lamp.fragment = True
        self.lamp.prelude = b"\xf5" + extended_reply(system_reply(255)) + b"\xf6"
        state = await self.client.refresh()
        self.assertEqual(state.channels, self.lamp.channels)
        self.assertEqual(state.system.mode_raw, 1)

    async def test_both_orders_preserve_other_five_channels_and_confirm_manual(self):
        for controller in ((0x12, 0x3C), (0x14, 0x32)):
            with self.subTest(controller=controller):
                self.lamp.controller = controller
                self.lamp.mode = 0
                self.lamp.channels = (10, 20, 30, 40, 50, 60)
                expected = await self.client.refresh()
                state = await self.client.set_channel(2, 35, expected_state=expected)
                self.assertEqual(state.channels, (10, 20, 35, 40, 50, 60))
                self.assertEqual(state.system.mode_raw, 1)
                channel_command, manual = self.lamp.writes[-2:]
                wire = (10, 20, 40, 35, 50, 60) if controller == (0x14, 0x32) else state.channels
                self.assertEqual(channel_command[3:9], bytes(wire))
                self.assertEqual(manual, protocol.mode_frame(1))
                write_events = [event for event in self.lamp.observed if event[1][2] == 0xFA]
                self.assertGreaterEqual(write_events[-1][2] - write_events[-2][2], 0.09)
                self.assertNotEqual(write_events[-1][0], self.lamp.observed[-1][0])

    async def test_all_six_channels_and_zero_hundred_endpoints(self):
        await self.client.refresh()
        for index in range(6):
            for value in (0, 100):
                before = self.lamp.channels
                state = await self.client.set_channel(index, value)
                expected = list(before)
                expected[index] = value
                self.assertEqual(state.channels, tuple(expected))

    async def test_explicit_modes_are_verified_on_fresh_read_connection(self):
        await self.client.refresh()
        for mode in (0, 1):
            state = await self.client.set_mode(mode)
            self.assertEqual(state.system.mode_raw, mode)
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(mode) for mode in (0, 1)])

    async def test_shipped_profile_allows_explicit_manual_and_automatic_only(self):
        self.profiles.stop()
        self.lamp.controller = (28, 30)
        self.lamp.version = (26, 29)
        self.lamp.mode = 0
        state = await self.client.refresh()
        self.assertTrue(state.system.write_supported)
        self.assertEqual(self.lamp.writes, [])
        changed = await self.client.set_channel(0, 9, expected_state=state)
        self.assertEqual(changed.channels, (9, 20, 30, 40, 50, 60))
        self.assertEqual(changed.system.mode_raw, 1)
        self.assertEqual((await self.client.set_mode(0)).system.mode_raw, 0)
        frames = list(self.lamp.frames)
        with self.assertRaises(protocol.ProtocolError):
            await self.client.set_mode(8)
        self.assertEqual(self.lamp.frames, frames)

    async def test_shutdown_origin_is_readable_but_blocks_channels_and_mode(self):
        self.lamp.mode = 8
        for action in (lambda: self.client.set_channel(0, 9), lambda: self.client.set_mode(0)):
            state = await self.client.refresh()
            self.assertEqual(state.system.mode_raw, 8)
            with self.assertRaises(client.UnsupportedDeviceError):
                await action()
        self.assertEqual(self.lamp.writes, [])

    async def test_unknown_mode_is_readable_but_blocks_any_write(self):
        self.lamp.mode = 255
        state = await self.client.refresh()
        self.assertEqual(state.system.mode_raw, 255)
        with self.assertRaises(client.UnsupportedDeviceError):
            await self.client.set_channel(0, 11)
        self.assertEqual(self.lamp.writes, [])

    async def test_unverified_profile_is_readable_but_cannot_write(self):
        self.lamp.version = (2, 6)
        state = await self.client.refresh()
        self.assertFalse(state.system.write_supported)
        with self.assertRaises(client.UnsupportedDeviceError):
            await self.client.set_mode(1)
        self.assertEqual(self.lamp.writes, [])

    async def test_invalid_values_never_open_connection_or_coerce(self):
        for value in (-1, 101, 255, True, 1.0, "10", None):
            with self.subTest(value=value), self.assertRaises(protocol.ProtocolError):
                await self.client.set_channel(0, value)
        for index in (-1, 6, True, 1.0):
            with self.subTest(index=index), self.assertRaises(protocol.ProtocolError):
                await self.client.set_channel(index, 10)
        for mode in (2, 8, True, 1.0):
            with self.assertRaises(protocol.ProtocolError):
                await self.client.set_mode(mode)
        self.assertEqual(self.lamp.connections, 0)

    async def test_first_write_requires_a_successful_refresh(self):
        with self.assertRaises(client.RefreshRequiredError):
            await self.client.set_channel(0, 11)
        self.assertEqual(self.lamp.connections, 0)

    async def test_prewrite_competing_controller_aborts_without_overriding(self):
        expected = await self.client.refresh()
        self.lamp.channels = (10, 20, 30, 40, 51, 60)
        with self.assertRaises(client.ConflictError):
            await self.client.set_channel(0, 11, expected_state=expected)
        self.assertEqual(self.lamp.writes, [])
        self.assertIsNone(self.client.last_state)

    async def test_explicit_channel_change_during_automatic_preserves_fresh_other_channels(self):
        self.lamp.mode = protocol.MODE_AUTOMATIC
        observed = await self.client.refresh()
        fresh = (12, 24, 36, 48, 60, 72)
        self.lamp.channels = fresh
        state = await self.client.set_channel(2, 35, expected_state=observed)
        self.assertEqual(state.channels, (12, 24, 35, 48, 60, 72))
        self.assertEqual(state.system.mode_raw, protocol.MODE_MANUAL)
        self.assertEqual(
            self.lamp.writes,
            [
                protocol.channel_write_frame(state.channels),
                protocol.mode_frame(protocol.MODE_MANUAL),
            ],
        )

    async def test_explicit_manual_selection_allows_automatic_channel_drift(self):
        self.lamp.mode = protocol.MODE_AUTOMATIC
        observed = await self.client.refresh()
        fresh = (12, 24, 36, 48, 60, 72)
        self.lamp.channels = fresh
        state = await self.client.set_mode(protocol.MODE_MANUAL, expected_state=observed)
        self.assertEqual(state.channels, fresh)
        self.assertEqual(state.system.mode_raw, protocol.MODE_MANUAL)
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(protocol.MODE_MANUAL)])

    async def test_automatic_drift_does_not_allow_changed_mode_or_profile(self):
        for changed_field, changed_value in (
            ("mode", protocol.MODE_MANUAL),
            ("version", (2, 6)),
            ("controller", (0x14, 0x32)),
            ("count", 3),
        ):
            with self.subTest(field=changed_field):
                self.lamp.mode = protocol.MODE_AUTOMATIC
                self.lamp.version = (2, 5)
                self.lamp.controller = (0x12, 0x3C)
                self.lamp.count = 6
                self.lamp.channels = (10, 20, 30, 40, 50, 60)
                observed = await self.client.refresh()
                self.lamp.channels = (12, 24, 36, 48, 60, 72)
                setattr(self.lamp, changed_field, changed_value)
                with self.assertRaises(client.ConflictError):
                    await self.client.set_channel(0, 11, expected_state=observed)
                self.assertEqual(self.lamp.writes, [])

    async def test_automatic_poll_drift_never_causes_a_command(self):
        self.lamp.mode = protocol.MODE_AUTOMATIC
        await self.client.refresh()
        self.lamp.channels = (12, 24, 36, 48, 60, 72)
        state = await self.client.refresh()
        self.assertEqual(state.channels, self.lamp.channels)
        self.assertEqual(self.lamp.writes, [])

    async def test_postwrite_competing_controller_aborts_without_restore_or_retry(self):
        await self.client.refresh()

        async def interfere(connection, frame):
            if connection == 3 and frame == protocol.SYSTEM_QUERY:
                self.lamp.channels = (11, 20, 30, 40, 51, 60)

        self.lamp.hook = interfere
        with self.assertRaises(client.ConflictError):
            await self.client.set_channel(0, 11)
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertEqual(self.lamp.channels[4], 51)
        with self.assertRaises(client.RefreshRequiredError):
            await self.client.set_channel(0, 10)
        self.assertEqual(len(self.lamp.writes), 2)

    async def test_profile_change_during_write_is_a_conflict(self):
        await self.client.refresh()

        async def interfere(connection, frame):
            if connection == 3 and frame == protocol.SYSTEM_QUERY:
                self.lamp.version = (2, 6)

        self.lamp.hook = interfere
        with self.assertRaises(client.ConflictError):
            await self.client.set_channel(0, 11)

    async def test_write_echo_and_ack_cannot_confirm_failed_device_write(self):
        self.lamp.channel_operation = 0xFA
        self.lamp.ignore_writes = True
        self.lamp.echo_writes = True
        await self.client.refresh()
        with self.assertRaises(client.ConflictError):
            await self.client.set_channel(0, 11)
        self.assertEqual(self.lamp.channels[0], 10)
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertEqual(self.lamp.connections, 3)

    async def test_write_connection_stays_for_queried_mode_after_delayed_processing(self):
        self.lamp.channel_operation = 0xFA
        self.lamp.fragment = True
        self.lamp.echo_writes = True
        self.lamp.mode = protocol.MODE_AUTOMATIC
        await self.client.refresh()
        processed = asyncio.Event()
        barrier_seen = asyncio.Event()

        async def delayed_processing(connection, frame):
            if frame == protocol.mode_frame(protocol.MODE_MANUAL):
                # Simulator-only latency, not a claim about the real controller.
                await asyncio.sleep(0.08)
                processed.set()
            if connection == 2 and frame == protocol.SYSTEM_QUERY and self.lamp.writes:
                self.assertTrue(processed.is_set())
                barrier_seen.set()

        self.lamp.hook = delayed_processing
        state = await self.client.set_channel(0, 9)
        self.assertTrue(barrier_seen.is_set())
        self.assertEqual(state.channels, (9, 20, 30, 40, 50, 60))
        self.assertEqual(state.system.mode_raw, protocol.MODE_MANUAL)
        self.assertEqual(self.lamp.connections, 3)
        write_session = [
            (frame, when) for connection, frame, when in self.lamp.observed if connection == 2
        ]
        mode_at = next(when for frame, when in write_session if frame == protocol.mode_frame(1))
        barrier_at = [when for frame, when in write_session if frame == protocol.SYSTEM_QUERY][-1]
        self.assertGreaterEqual(barrier_at - mode_at, client.WRITE_DRAIN_PAUSE - 0.01)
        self.assertEqual(
            [frame for connection, frame, _time in self.lamp.observed if connection == 2],
            [
                protocol.SYSTEM_QUERY,
                protocol.CHANNEL_QUERY,
                protocol.channel_write_frame(state.channels),
                protocol.mode_frame(protocol.MODE_MANUAL),
                protocol.SYSTEM_QUERY,
            ],
        )
        self.assertEqual(
            [frame for connection, frame, _time in self.lamp.observed if connection == 3],
            [protocol.SYSTEM_QUERY, protocol.CHANNEL_QUERY],
        )

    async def test_unconfirmed_barrier_mode_stops_before_reconnect_without_retry(self):
        self.lamp.mode = protocol.MODE_AUTOMATIC
        await self.client.refresh()
        self.lamp.ignore_writes = True
        with self.assertRaisesRegex(client.ConflictError, "before disconnect"):
            await self.client.set_mode(protocol.MODE_MANUAL)
        self.assertEqual(self.lamp.connections, 2)
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(protocol.MODE_MANUAL)])
        self.assertIsNone(self.client.last_state)

    async def test_write_echo_without_queried_system_reply_does_not_satisfy_barrier(self):
        await self.client.refresh()

        def only_echo_barrier(frame, response):
            if frame == protocol.SYSTEM_QUERY and self.lamp.writes:
                return protocol.mode_frame(protocol.MODE_MANUAL)
            return response

        self.lamp.response_override = only_echo_barrier
        with self.assertRaises(client.AquariusError):
            await self.client.set_channel(0, 9)
        self.assertEqual(self.lamp.connections, 2)
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertIsNone(self.client.last_state)

    async def test_profile_change_at_barrier_stops_before_reconnect(self):
        await self.client.refresh()

        async def changed_profile(connection, frame):
            if connection == 2 and frame == protocol.SYSTEM_QUERY and self.lamp.writes:
                self.lamp.version = (2, 6)

        self.lamp.hook = changed_profile
        with self.assertRaises(client.ConflictError):
            await self.client.set_channel(0, 9)
        self.assertEqual(self.lamp.connections, 2)
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertIsNone(self.client.last_state)

    async def test_unexpected_status_during_postwrite_quarantine_is_not_a_barrier(self):
        await self.client.refresh()

        def unsolicited_status(frame, response):
            if frame == protocol.mode_frame(protocol.MODE_MANUAL):
                return system_reply(mode=protocol.MODE_MANUAL)
            return response

        self.lamp.response_override = unsolicited_status
        with self.assertRaises(protocol.ProtocolError):
            await self.client.set_channel(0, 9)
        self.assertEqual(self.lamp.connections, 2)
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertEqual(
            sum(
                connection == 2 and frame == protocol.SYSTEM_QUERY
                for connection, frame, _when in self.lamp.observed
            ),
            1,
        )
        self.assertIsNone(self.client.last_state)

    async def test_unexpected_status_after_channel_blocks_manual_save(self):
        await self.client.refresh()
        channel_command = protocol.channel_write_frame((9, 20, 30, 40, 50, 60))

        def unsolicited_status(frame, response):
            if frame == channel_command:
                return system_reply(mode=protocol.MODE_MANUAL)
            return response

        self.lamp.response_override = unsolicited_status
        with self.assertRaises(protocol.ProtocolError):
            await self.client.set_channel(0, 9)
        self.assertEqual(self.lamp.connections, 2)
        self.assertEqual(self.lamp.writes, [channel_command])
        self.assertIsNone(self.client.last_state)

    async def test_concurrent_updates_serialize_entire_read_modify_write(self):
        await self.client.refresh()
        first, second = await asyncio.gather(
            self.client.set_channel(0, 11), self.client.set_channel(1, 21)
        )
        self.assertEqual(first.channels, (11, 20, 30, 40, 50, 60))
        self.assertEqual(second.channels, (11, 21, 30, 40, 50, 60))
        self.assertEqual(
            self.lamp.frames,
            [protocol.SYSTEM_QUERY, protocol.CHANNEL_QUERY]
            + [
                protocol.SYSTEM_QUERY,
                protocol.CHANNEL_QUERY,
                protocol.channel_write_frame(first.channels),
                protocol.mode_frame(1),
                protocol.SYSTEM_QUERY,
                protocol.SYSTEM_QUERY,
                protocol.CHANNEL_QUERY,
            ]
            + [
                protocol.SYSTEM_QUERY,
                protocol.CHANNEL_QUERY,
                protocol.channel_write_frame(second.channels),
                protocol.mode_frame(1),
                protocol.SYSTEM_QUERY,
                protocol.SYSTEM_QUERY,
                protocol.CHANNEL_QUERY,
            ],
        )

    async def test_stale_concurrent_explicit_state_is_a_conflict(self):
        expected = await self.client.refresh()
        results = await asyncio.gather(
            self.client.set_channel(0, 11, expected),
            self.client.set_channel(1, 21, expected),
            return_exceptions=True,
        )
        self.assertIsInstance(results[0], client.DeviceState)
        self.assertIsInstance(results[1], client.ConflictError)
        self.assertEqual(self.lamp.channels, (11, 20, 30, 40, 50, 60))

    async def test_failed_write_and_queued_write_are_never_replayed(self):
        await self.client.refresh()
        self.lamp.ignore_writes = True
        results = await asyncio.gather(
            self.client.set_channel(0, 11), self.client.set_channel(1, 21), return_exceptions=True
        )
        self.assertIsInstance(results[0], client.ConflictError)
        self.assertIsInstance(results[1], client.RefreshRequiredError)
        self.assertEqual(len(self.lamp.writes), 2)
        self.lamp.ignore_writes = False
        await self.client.refresh()
        self.assertEqual(len(self.lamp.writes), 2)
        self.assertEqual(self.lamp.channels, (10, 20, 30, 40, 50, 60))
        state = await self.client.set_channel(0, 12)
        self.assertEqual(state.channels[0], 12)

    async def test_query_echo_is_not_a_valid_device(self):
        self.lamp.response_override = lambda frame, response: frame
        with self.assertRaises(protocol.ProtocolError):
            await self.client.refresh()
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY])

    async def test_valid_system_plus_channel_query_echo_cannot_supply_false_zeroes(self):
        self.lamp.response_override = (
            lambda frame, response: frame if frame == protocol.CHANNEL_QUERY else response
        )
        with self.assertRaises(protocol.ProtocolError):
            await self.client.refresh()
        self.assertIsNone(self.client.last_state)
        with self.assertRaises(client.RefreshRequiredError):
            await self.client.set_channel(0, 11)
        self.assertEqual(self.lamp.writes, [])
        self.assertEqual(self.lamp.channels, (10, 20, 30, 40, 50, 60))

    async def test_channel_query_echo_during_prewrite_never_wipes_other_channels(self):
        await self.client.refresh()
        self.lamp.response_override = (
            lambda frame, response: frame if frame == protocol.CHANNEL_QUERY else response
        )
        with self.assertRaises(protocol.ProtocolError):
            await self.client.set_channel(0, 11)
        self.assertEqual(self.lamp.writes, [])
        self.assertEqual(self.lamp.channels, (10, 20, 30, 40, 50, 60))

    async def test_unambiguous_fa_all_off_response_preserves_zero_baseline(self):
        self.lamp.channel_operation = 0xFA
        self.lamp.channels = (0, 0, 0, 0, 0, 0)
        state = await self.client.refresh()
        self.assertEqual(state.channels, (0, 0, 0, 0, 0, 0))
        state = await self.client.set_channel(0, 1)
        self.assertEqual(state.channels, (1, 0, 0, 0, 0, 0))

    async def test_ambiguous_fc_all_off_response_fails_closed(self):
        self.lamp.channel_operation = 0xFC
        self.lamp.channels = (0, 0, 0, 0, 0, 0)
        with self.assertRaises(protocol.ProtocolError):
            await self.client.refresh()
        self.assertEqual(self.lamp.writes, [])

    async def test_stale_channel_frame_before_query_is_rejected_at_every_split(self):
        stale = channels_reply((1, 2, 3, 4, 5, 6), operation=0xFA)
        fresh = channels_reply(operation=0xFA)

        class ScriptedReader:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            async def read(self, size):
                return self.chunks.pop(0) if self.chunks else b""

        class ScriptedWriter:
            def __init__(self):
                self.frames = []

            def write(self, frame):
                self.frames.append(frame)

            async def drain(self):
                pass

            def close(self):
                pass

            async def wait_closed(self):
                pass

        for split in range(len(stale) + 1):
            with self.subTest(split=split):
                self.client._reader = ScriptedReader(
                    [system_reply() + stale[:split], stale[split:] + fresh]
                )
                self.client._writer = ScriptedWriter()
                self.client._decoder = protocol.StreamDecoder()
                with self.assertRaises(protocol.ProtocolError):
                    await self.client._read_state()
                self.assertEqual(self.client._writer.frames, [protocol.SYSTEM_QUERY])

    async def test_unsolicited_status_arriving_during_query_pause_is_rejected(self):
        system_seen = asyncio.Event()

        async def observe(connection, frame):
            if frame == protocol.SYSTEM_QUERY:
                system_seen.set()

        self.lamp.hook = observe
        refresh = asyncio.create_task(self.client.refresh())
        await asyncio.wait_for(system_seen.wait(), 1)
        await asyncio.sleep(0.02)
        for writer in tuple(self.lamp.writers):
            writer.write(channels_reply((1, 2, 3, 4, 5, 6), operation=0xFA))
            await writer.drain()
        with self.assertRaises(protocol.ProtocolError):
            await refresh
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY])
        self.assertEqual(self.lamp.writes, [])

    async def test_partial_unsolicited_frame_at_query_boundary_fails_closed(self):
        system_seen = asyncio.Event()

        async def observe(connection, frame):
            if frame == protocol.SYSTEM_QUERY:
                system_seen.set()

        self.lamp.hook = observe
        refresh = asyncio.create_task(self.client.refresh())
        await asyncio.wait_for(system_seen.wait(), 1)
        await asyncio.sleep(0.02)
        for writer in tuple(self.lamp.writers):
            writer.write(channels_reply(operation=0xFA)[:7])
            await writer.drain()
        with self.assertRaises(protocol.ProtocolError):
            await refresh
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY])

    async def test_ack_and_extended_payload_during_pause_do_not_supply_channel_status(self):
        system_seen = asyncio.Event()

        async def observe(connection, frame):
            if frame == protocol.SYSTEM_QUERY:
                system_seen.set()

        self.lamp.hook = observe
        refresh = asyncio.create_task(self.client.refresh())
        await asyncio.wait_for(system_seen.wait(), 1)
        await asyncio.sleep(0.02)
        for writer in tuple(self.lamp.writers):
            writer.write(b"\xf5" + extended_reply(channels_reply((1, 2, 3, 4, 5, 6))))
            await writer.drain()
        state = await refresh
        self.assertEqual(state.channels, (10, 20, 30, 40, 50, 60))
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY, protocol.CHANNEL_QUERY])

    async def test_acknowledgement_only_response_times_out_without_write(self):
        self.lamp.response_override = lambda frame, response: b"\xf5"
        self.client.timeout = 0.05
        with self.assertRaises(client.AquariusError):
            await self.client.refresh()
        self.assertEqual(self.lamp.frames, [protocol.SYSTEM_QUERY])
        self.assertIsNone(self.client.last_state)

    async def test_eof_invalid_percentages_and_receive_flood_fail_closed(self):
        def invalid_channel(frame, response):
            return (
                channels_reply((255, 0, 0, 0, 0, 0))
                if frame == protocol.CHANNEL_QUERY
                else response
            )

        self.lamp.response_override = invalid_channel
        with self.assertRaises(protocol.ProtocolError):
            await self.client.refresh()
        self.lamp.response_override = lambda frame, response: b"x" * (client.MAX_RECEIVED_BYTES + 1)
        with self.assertRaises(protocol.ProtocolError):
            await self.client.refresh()
        self.lamp.response_override = None

        async def eof(connection, frame):
            for writer in tuple(self.lamp.writers):
                writer.close()

        self.lamp.hook = eof
        with self.assertRaises(client.AquariusError):
            await self.client.refresh()
        self.assertEqual(self.lamp.writes, [])

    async def test_cancel_during_manual_pause_does_not_send_mode_or_restore(self):
        await self.client.refresh()
        write_seen = asyncio.Event()

        async def observe(connection, frame):
            if frame[1:3] == b"\xe2\xfa":
                write_seen.set()

        self.lamp.hook = observe
        pending = asyncio.create_task(self.client.set_channel(0, 11))
        await asyncio.wait_for(write_seen.wait(), 1)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        await asyncio.sleep(0.11)
        self.assertEqual(self.lamp.writes, [protocol.channel_write_frame((11, 20, 30, 40, 50, 60))])
        with self.assertRaises(client.RefreshRequiredError):
            await self.client.set_channel(0, 10)
        await self.client.refresh()
        self.assertEqual(len(self.lamp.writes), 1)

    async def test_unload_cancels_stalled_transaction_and_permanently_closes(self):
        query_seen = asyncio.Event()

        async def observe(connection, frame):
            query_seen.set()

        self.lamp.hook = observe
        self.lamp.response_override = lambda frame, response: None
        pending = asyncio.create_task(self.client.refresh())
        await asyncio.wait_for(query_seen.wait(), 1)
        await asyncio.wait_for(self.client.close(), 1)
        self.assertTrue(pending.cancelled())
        with self.assertRaises(client.AquariusError):
            await self.client.refresh()
        self.assertEqual(self.lamp.writes, [])

    async def test_cancel_during_socket_cleanup_invalidates_state_and_active_task(self):
        previous = await self.client.refresh()
        waiting = asyncio.Event()

        class WaitingWriter:
            def close(self):
                pass

            async def wait_closed(self):
                waiting.set()
                await asyncio.Event().wait()

        self.client._writer = WaitingWriter()
        with patch.object(self.client, "_connected_operation", return_value=previous):
            pending = asyncio.create_task(self.client.refresh())
            await asyncio.wait_for(waiting.wait(), 1)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertIsNone(self.client.last_state)
        self.assertIsNone(self.client._active_task)
        self.assertTrue(self.client._needs_refresh)
        with self.assertRaises(client.RefreshRequiredError):
            await self.client.set_channel(0, 11)

    async def test_constructor_rejects_unbounded_timeout_and_invalid_endpoint(self):
        for timeout in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                client.AquariusClient("127.0.0.1", timeout=timeout)
        for port in (0, 65536, True, 8080.0):
            with self.subTest(port=port), self.assertRaises(ValueError):
                client.AquariusClient("127.0.0.1", port)
        with self.assertRaises(ValueError):
            client.AquariusClient("")

    async def test_power_profile_gate_is_separate_from_manual_control(self):
        await self.client.refresh()
        with self.assertRaises(client.UnsupportedDeviceError):
            await self.client.turn_off()
        self.lamp.mode = 8
        await self.client.refresh()
        with self.assertRaises(client.UnsupportedDeviceError):
            await self.client.turn_on()
        self.assertEqual(self.lamp.writes, [])

    async def test_exact_validated_profile_is_the_only_shipped_power_admission(self):
        self.assertEqual(protocol.VERIFIED_SHUTDOWN_PROFILES, {((28, 30), (26, 29), 6)})
        self.profiles.stop()
        self.lamp.controller, self.lamp.version = (28, 30), (26, 29)
        state = await self.client.refresh()
        self.assertTrue(state.system.power_supported)
        self.assertEqual(self.lamp.writes, [])
        self.lamp.version = (26, 30)
        state = await self.client.refresh()
        self.assertFalse(state.system.power_supported)
        with self.assertRaises(client.UnsupportedDeviceError):
            await self.client.turn_off()
        self.assertEqual(self.lamp.writes, [])

    async def test_explicit_power_off_and_saved_manual_mix_round_trip(self):
        self.lamp.controller = (0x14, 0x32)
        self.lamp.channel_operation = 0xFA
        original = self.lamp.channels
        with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES):
            observed = await self.client.refresh()
            off = await self.client.turn_off(expected_state=observed)
            self.assertEqual(off.system.mode_raw, 8)
            restored = await self.client.turn_on(original, expected_state=off)
        self.assertEqual(restored.channels, original)
        self.assertEqual(restored.system.mode_raw, 1)
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(8), protocol.mode_frame(1)])

    async def test_explicit_power_zero_reply_and_automatic_restore_never_sends_channels(self):
        self.lamp.mode = 0
        self.lamp.channel_operation = 0xFA

        def zero_off(frame, response):
            if frame == protocol.mode_frame(8):
                self.lamp.channels = (0,) * 6
            return response

        self.lamp.response_override = zero_off
        with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES):
            await self.client.refresh()
            off = await self.client.turn_off()
            self.assertEqual(off.channels, (0,) * 6)
            on = await self.client.turn_on(expected_state=off)
        self.assertEqual(on.system.mode_raw, 0)
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(8), protocol.mode_frame(0)])

    async def test_power_readback_changed_profile_fails_without_retry(self):
        with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES):
            await self.client.refresh()

            async def interfere(connection, frame):
                if connection == 3 and frame == protocol.SYSTEM_QUERY:
                    self.lamp.version = (2, 6)

            self.lamp.hook = interfere
            with self.assertRaises(client.ConflictError):
                await self.client.turn_off()
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(8)])
        self.assertIsNone(self.client.last_state)

    async def test_off_unexpected_mixed_vector_is_not_treated_as_safe_shutdown(self):
        with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES):
            await self.client.refresh()

            def mixed_off(frame, response):
                if frame == protocol.mode_frame(8):
                    self.lamp.channels = (0, 20, 30, 40, 50, 60)
                return response

            self.lamp.response_override = mixed_off
            with self.assertRaises(client.ConflictError):
                await self.client.turn_off()
        self.assertEqual(self.lamp.writes, [protocol.mode_frame(8)])

    async def test_manual_power_restore_rejects_invalid_or_zero_mix_before_io(self):
        for channels in ((0,) * 6, (1,) * 5, (101,) * 6, (True,) * 6, (1.0,) * 6):
            with self.subTest(channels=channels), self.assertRaises(protocol.ProtocolError):
                await self.client.turn_on(channels)
        self.assertEqual(self.lamp.connections, 0)

    async def test_off_state_requires_fresh_exact_vector_before_manual_restore(self):
        with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES):
            self.lamp.mode = 8
            observed = await self.client.refresh()
            self.lamp.channels = (11, 20, 30, 40, 50, 60)
            with self.assertRaises(client.ConflictError):
                await self.client.turn_on(observed.channels, expected_state=observed)
        self.assertEqual(self.lamp.writes, [])


if __name__ == "__main__":
    unittest.main()

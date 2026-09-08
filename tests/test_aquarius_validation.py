"""Autonomous cleanup and native TCP simulation, using fictional state only."""

import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.aquarius_tcp_helpers import channels_reply, extended_reply, protocol, system_reply
from tooling import aquarius_validation as validation


def config_data():
    return {
        "schema_version": 1,
        "host": "127.0.0.1",
        "port": 8080,
        "profile": {
            "controller_bytes": [0x12, 0x3C],
            "version_bytes": [2, 5],
            "channel_count_raw": 6,
        },
        "channel_index": 0,
        "delta": -1,
    }


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds

    def advance(self, seconds, deadline):
        if self.value + seconds > deadline:
            self.value = deadline
            raise validation.DeadlineError("synthetic deadline")
        self.value += seconds


class Simulator:
    """Measured deterministic faults; each phase obeys the worker's absolute deadline."""

    def __init__(self):
        self.clock = FakeClock()
        self.state = validation.State(0, (0x12, 0x3C), (2, 5), 6, (10, 20, 30, 40, 50, 60))
        self.original = self.state
        self.writes = []
        self.connections = 0
        self.closed = 0
        self.hook = None
        self.worker = None

    def event(self, name):
        if self.hook is not None:
            self.hook(name, self)

    def factory(self, config, deadline, clock):
        simulator = self
        self.clock.advance(0.03, deadline)
        self.connections += 1
        self.event("connect")

        class Session:
            phase = "connected"
            last_system = None

            def close(self):
                simulator.closed += 1

            def read_state(self, deadline):
                self.phase = "system_query_reply"
                self.read_deadline = deadline
                simulator.clock.advance(0.4, deadline)
                simulator.event("read")
                return simulator.state

            def system(self, deadline):
                simulator.clock.advance(0.12, deadline)
                simulator.event("system")
                state = simulator.state
                return state.mode, state.controller, state.version, state.count

            def send(self, command, deadline):
                simulator.clock.advance(0.02, deadline)
                simulator.writes.append((simulator.clock(), command))
                if command[1:3] == b"\xe2\xfa":
                    values = list(command[3:9])
                    if simulator.state.controller == (0x14, 0x32):
                        values[2], values[3] = values[3], values[2]
                    simulator.state = replace(simulator.state, channels=tuple(values))
                    simulator.event("channel_sent")
                elif command[1:4] == b"\xe1\xfa\xdb":
                    simulator.state = replace(simulator.state, mode=command[4])
                    simulator.event("mode_sent")
                else:
                    raise AssertionError("unexpected synthetic write")

            def quarantine(self, duration, deadline, echoes=()):
                simulator.clock.advance(duration, deadline)
                simulator.event("quarantine")

        return Session()

    def run(self, **kwargs):
        config = validation.Configuration.parse(config_data(), simulation=True)
        self.worker = validation.ValidationWorker(
            config,
            session_factory=self.factory,
            clock=self.clock,
            sleeper=self.clock.sleep,
            **kwargs,
        )
        return self.worker.run()


class ValidationTransactionTests(unittest.TestCase):
    def test_success_changes_one_channel_and_restores_channels_and_original_mode(self):
        simulator = Simulator()
        result = simulator.run()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], 5)
        commands = [command for _, command in simulator.writes]
        self.assertEqual(
            commands,
            [
                validation.channel_frame((9, 20, 30, 40, 50, 60), simulator.state.controller),
                validation.mode_frame(1),
                validation.channel_frame(simulator.original.channels, simulator.state.controller),
                validation.mode_frame(1),
                validation.mode_frame(0),
            ],
        )
        stages = [event["stage"] for event in result["events"]]
        self.assertLess(
            stages.index("restore_channels_confirmed"), stages.index("recovery_confirmed")
        )
        self.assertGreaterEqual(simulator.connections, 5)
        self.assertEqual(simulator.connections, simulator.closed)

    def test_manual_baseline_restored_without_automatic_command(self):
        simulator = Simulator()
        simulator.state = simulator.original = replace(simulator.original, mode=1)
        self.assertEqual(simulator.run()["status"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertNotIn(validation.mode_frame(0), [frame for _, frame in simulator.writes])

    def test_exception_after_channel_write_enters_cleanup_without_next_turn(self):
        simulator = Simulator()

        def fault(event, sim):
            if event == "channel_sent" and len(sim.writes) == 1:
                raise RuntimeError("synthetic failure after device mutation")

        simulator.hook = fault
        result = simulator.run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], validation.MAX_EXCURSION)

    def test_cancellation_after_mutation_and_repeated_cleanup_signals_restore(self):
        simulator = Simulator()

        def cancel(event, sim):
            if event in ("channel_sent", "mode_sent"):
                sim.worker.request_stop()

        simulator.hook = cancel
        result = simulator.run()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)

    def test_full_experiment_budget_still_leaves_measured_cleanup_reserve(self):
        simulator = Simulator()

        def timeout(event, sim):
            if event == "system" and not sim.worker.cleaning:
                sim.clock.value = sim.worker.excursion_started + validation.EXPERIMENT_SECONDS
                raise validation.DeadlineError("synthetic slow verification")

        simulator.hook = timeout
        result = simulator.run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertLess(result["excursion_seconds"], validation.MAX_EXCURSION)
        recovery = next(event for event in result["events"] if event["stage"] == "recovery_started")
        self.assertEqual(recovery["excursion_seconds"], validation.EXPERIMENT_SECONDS)
        self.assertEqual(simulator.state, simulator.original)

    def test_lost_verification_connection_recovery_reads_before_any_restore(self):
        simulator = Simulator()
        failed = False

        def disconnect(event, sim):
            nonlocal failed
            if event == "read" and sim.writes and not failed:
                failed = True
                raise ConnectionResetError("synthetic lost verification connection")

        simulator.hook = disconnect
        result = simulator.run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)

    def test_network_loss_reports_unconfirmed_recovery_without_blind_restore(self):
        simulator = Simulator()

        def disconnect(event, sim):
            if event in ("read", "connect") and sim.writes:
                raise ConnectionResetError("synthetic outage")

        simulator.hook = disconnect
        result = simulator.run()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        self.assertNotEqual(simulator.state, simulator.original)
        attempts = [
            event for event in result["events"] if event["stage"] == "recovery_guard_read_attempt"
        ]
        self.assertEqual(len(attempts), validation.RECOVERY_READ_ATTEMPTS)

    def test_first_recovery_connection_or_read_failure_retries_fresh_read_only(self):
        for failure_event, error in (
            ("connect", ConnectionRefusedError),
            ("read", TimeoutError),
            ("read", EOFError),
        ):
            with self.subTest(failure_event=failure_event, error=error):
                simulator = Simulator()
                failed = False

                def transient(event, sim):
                    nonlocal failed
                    if sim.worker.cleaning and event == failure_event and not failed:
                        failed = True
                        sim.clock.sleep(0.8 if failure_event == "connect" else 0.4)
                        raise error("synthetic first recovery transport failure")

                simulator.hook = transient
                result = simulator.run()
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(len(simulator.writes), 5)
                self.assertLess(result["excursion_seconds"], 10)
                failures = [
                    event
                    for event in result["events"]
                    if event["stage"] == "recovery_guard_read_transport_failed"
                ]
                self.assertEqual(len(failures), 1)
                self.assertEqual(
                    failures[0]["phase"],
                    "connect" if failure_event == "connect" else "system_query_reply",
                )
                attempts = [
                    event
                    for event in result["events"]
                    if event["stage"] == "recovery_guard_read_attempt"
                ]
                self.assertEqual(len(attempts), 2)
                self.assertEqual(
                    attempts[0]["deadline_monotonic_seconds"],
                    attempts[1]["deadline_monotonic_seconds"],
                )
                self.assertEqual(attempts[0]["command_reserve_seconds"], 4)

    def test_full_experiment_budget_and_transient_guard_timeout_still_recover(self):
        simulator = Simulator()
        failed = False

        def transient(event, sim):
            nonlocal failed
            if event == "system" and not sim.worker.cleaning:
                sim.clock.value = sim.worker.excursion_started + 3
                raise validation.DeadlineError("synthetic full experiment budget")
            if sim.worker.cleaning and event == "read" and not failed:
                failed = True
                sim.clock.sleep(0.4)
                raise TimeoutError("synthetic initial recovery guard timeout")

        simulator.hook = transient
        result = simulator.run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS", result)
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], validation.RECOVERY_DEADLINE_SECONDS)
        restore_at = simulator.writes[2][0] - simulator.worker.excursion_started
        self.assertLess(restore_at, validation.RECOVERY_DEADLINE_SECONDS - 4)

    def test_restore_confirmation_read_retries_without_repeating_confirmed_writes(self):
        for write_count in (4, 5):
            with self.subTest(write_count=write_count):
                simulator = Simulator()
                failed = False

                def transient(event, sim):
                    nonlocal failed
                    if event == "read" and len(sim.writes) == write_count and not failed:
                        failed = True
                        raise ConnectionResetError("synthetic lost independent restore read")

                simulator.hook = transient
                result = simulator.run()
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(len(simulator.writes), 5)
                self.assertLess(result["excursion_seconds"], 10)

    def test_unsafe_profile_partial_or_competing_read_is_never_retried(self):
        for failure in ("profile", "partial", "competing"):
            with self.subTest(failure=failure):
                simulator = Simulator()
                guard_reads = 0

                def unsafe(event, sim):
                    nonlocal guard_reads
                    if event == "read" and sim.worker.cleaning:
                        guard_reads += 1
                        if failure == "partial":
                            raise validation.UnsafeState("synthetic ambiguous partial reply")
                        if failure == "profile":
                            sim.state = replace(sim.state, version=(2, 6))
                        else:
                            sim.state = replace(sim.state, channels=(9, 20, 30, 40, 51, 60))

                simulator.hook = unsafe
                result = simulator.run()
                self.assertEqual(result["recovery"], "FAIL")
                self.assertEqual(guard_reads, 1)
                self.assertEqual(len(simulator.writes), 2)
                self.assertFalse(
                    any(
                        event["stage"].endswith("_read_transport_failed")
                        for event in result["events"]
                    )
                )

    def test_observed_competing_mode_before_channel_timeout_is_not_retried(self):
        simulator = Simulator()
        guard_reads = 0

        def competing(event, sim):
            nonlocal guard_reads
            if event == "read" and sim.worker.cleaning:
                guard_reads += 1
                sim.worker.session.last_system = (0, (0x12, 0x3C), (2, 5), 6)
                raise TimeoutError("synthetic channels lost after competing Automatic status")

        simulator.hook = competing
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(guard_reads, 1)
        self.assertEqual(len(simulator.writes), 2)
        self.assertEqual(
            next(event for event in result["events"] if event["stage"] == "recovery_unconfirmed")[
                "reason"
            ],
            "UnsafeState",
        )

    def test_read_retry_budget_exhaustion_preserves_commands_reserve(self):
        simulator = Simulator()

        def timeouts(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.clock.advance(0.4, sim.worker.session.read_deadline)
                raise TimeoutError("synthetic recovery network loss")

        simulator.hook = timeouts
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        attempts = [
            event for event in result["events"] if event["stage"] == "recovery_guard_read_attempt"
        ]
        self.assertLessEqual(len(attempts), 3)
        self.assertLessEqual(
            simulator.clock(), attempts[0]["deadline_monotonic_seconds"] + 0.000001
        )

    def test_recovery_write_failure_is_never_retried(self):
        for failure_event in ("channel_sent", "mode_sent"):
            with self.subTest(failure_event=failure_event):
                simulator = Simulator()

                def uncertain(event, sim):
                    if event == failure_event and sim.worker.cleaning:
                        raise TimeoutError("synthetic uncertain recovery write")

                simulator.hook = uncertain
                result = simulator.run()
                self.assertEqual(result["recovery"], "FAIL")
                self.assertEqual(len(simulator.writes), 3 if failure_event == "channel_sent" else 4)
                self.assertEqual(simulator.connections, 3)

    def test_lost_cleanup_system_barrier_reply_uses_fresh_state_without_write_replay(self):
        for write_count in (4, 5):
            with self.subTest(write_count=write_count):
                simulator = Simulator()

                def uncertain(event, sim):
                    if event == "system" and len(sim.writes) == write_count:
                        raise TimeoutError("synthetic lost cleanup barrier reply")

                simulator.hook = uncertain
                result = simulator.run()
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(len(simulator.writes), 5)
                self.assertLess(result["excursion_seconds"], 10)

    def test_lost_cleanup_barrier_with_ignored_channels_stops_before_original_mode(self):
        simulator = Simulator()

        def ignored(event, sim):
            if event == "system" and sim.worker.cleaning:
                sim.state = replace(sim.state, channels=sim.worker.changed)
                raise EOFError("synthetic ignored channels and lost barrier reply")

        simulator.hook = ignored
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 4)
        self.assertEqual(simulator.state.mode, 1)
        self.assertEqual(simulator.state.channels, simulator.worker.changed)

    def test_unsafe_cleanup_barrier_reply_does_not_trigger_read_retry(self):
        simulator = Simulator()

        def ambiguous(event, sim):
            if event == "system" and sim.worker.cleaning:
                raise validation.UnsafeState("synthetic partial cleanup barrier")

        simulator.hook = ambiguous
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 4)
        self.assertEqual(simulator.connections, 3)

    def test_events_have_absolute_monotonic_timestamps_without_endpoint_details(self):
        result = Simulator().run()
        timestamps = [event["monotonic_seconds"] for event in result["events"]]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertTrue(all(value >= 100 for value in timestamps))
        self.assertNotIn("127.0.0.1", json.dumps(result))

    def test_competing_channel_change_stops_cleanup_without_snapshot_replay(self):
        simulator = Simulator()

        def interfere(event, sim):
            if event == "read" and sim.writes:
                sim.state = replace(sim.state, channels=(9, 20, 30, 40, 51, 60))

        simulator.hook = interfere
        result = simulator.run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        self.assertEqual(simulator.state.channels[4], 51)

    def test_automatic_schedule_changes_after_mode_restoration_are_preserved(self):
        simulator = Simulator()

        def schedule(event, sim):
            if event == "mode_sent" and sim.state.mode == 0:
                sim.state = replace(sim.state, channels=(12, 22, 32, 42, 52, 62))

        simulator.hook = schedule
        result = simulator.run()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(simulator.state.mode, 0)
        self.assertEqual(simulator.state.channels, (12, 22, 32, 42, 52, 62))

    def test_drifting_preflight_or_unknown_mode_never_sends_a_write(self):
        for change in ("channels", "mode", "profile"):
            with self.subTest(change=change):
                simulator = Simulator()
                reads = 0

                def drift(event, sim):
                    nonlocal reads
                    if event == "read":
                        reads += 1
                        if reads == 2:
                            updates = {
                                "channels": {"channels": (9, 20, 30, 40, 50, 60)},
                                "mode": {"mode": 77},
                                "profile": {"version": (2, 6)},
                            }
                            sim.state = replace(sim.state, **updates[change])

                simulator.hook = drift
                result = simulator.run()
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["recovery"], "NOT_REQUIRED")
                self.assertEqual(simulator.writes, [])

    def test_exhausted_recovery_budget_does_not_send_late_restore(self):
        simulator = Simulator()

        def slow_guard(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.clock.value = sim.worker.excursion_started + 8.5

        simulator.hook = slow_guard
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        self.assertLessEqual(result["excursion_seconds"], 10)

    def test_reporting_failure_after_mutation_does_not_disable_cleanup(self):
        simulator = Simulator()

        def failed_sink(report):
            if simulator.writes:
                raise OSError("synthetic full evidence disk")

        result = simulator.run(sink=failed_sink)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["reporting_error"])
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)

    def test_evidence_writes_are_deferred_until_after_cleanup_including_slow_fsync(self):
        simulator = Simulator()
        calls = []

        def slow_sink(report):
            calls.append((len(simulator.writes), simulator.state))
            if simulator.writes:
                self.assertEqual(simulator.state, simulator.original)
                simulator.clock.value += 30

        result = simulator.run(sink=slow_sink)
        self.assertEqual(result["status"], "PASS")
        self.assertLess(result["excursion_seconds"], 5)
        self.assertEqual([count for count, _ in calls if count], [5])

    def test_evidence_failure_before_first_write_aborts_without_an_excursion(self):
        simulator = Simulator()

        def failed_sink(report):
            raise OSError("synthetic disk failure")

        result = simulator.run(sink=failed_sink)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(result["recovery"], "NOT_REQUIRED")
        self.assertIsNone(result["excursion_seconds"])
        self.assertEqual(simulator.writes, [])

    def test_competing_manual_to_automatic_mode_change_is_never_overridden(self):
        simulator = Simulator()
        simulator.state = simulator.original = replace(simulator.original, mode=1)

        def competing(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.state = replace(sim.state, mode=0)

        simulator.hook = competing
        result = simulator.run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        self.assertEqual(simulator.state.mode, 0)

    def test_ambiguous_automatic_state_is_preserved_but_never_counts_as_recovery_pass(self):
        simulator = Simulator()

        def competing(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.state = replace(sim.state, mode=0, channels=(12, 22, 32, 42, 52, 62))

        simulator.hook = competing
        result = simulator.run()
        self.assertEqual(result["experiment"], "PASS")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(simulator.writes), 2)
        self.assertEqual(simulator.state.mode, 0)

    def test_signal_during_preflight_only_sets_flag_and_never_enters_test(self):
        simulator = Simulator()

        def cancel(event, sim):
            if event == "read":
                sim.worker.request_stop()

        simulator.hook = cancel
        result = simulator.run()
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(result["recovery"], "NOT_REQUIRED")
        self.assertEqual(simulator.writes, [])


class ValidationProtocolTests(unittest.TestCase):
    def test_worker_vectors_match_independent_module_protocol(self):
        self.assertEqual(validation.SYSTEM_QUERY, protocol.SYSTEM_QUERY)
        self.assertEqual(validation.CHANNEL_QUERY, protocol.CHANNEL_QUERY)
        for controller in ((0x12, 0x3C), (0x14, 0x32)):
            for channels in ((0, 100, 3, 4, 5, 6), (10, 20, 30, 40, 50, 60)):
                self.assertEqual(
                    validation.channel_frame(channels, controller),
                    protocol.channel_write_frame(channels, swap_cd=controller == (0x14, 0x32)),
                )
        for mode in (0, 1):
            self.assertEqual(validation.mode_frame(mode), protocol.mode_frame(mode))

    def test_decoder_fragmentation_embedded_markers_and_extended_messages(self):
        response = bytearray(system_reply())
        response[12:16] = b"\xf1\xf3\xf5\xf6"
        raw = b"\xf5" + extended_reply(channels_reply()) + bytes(response) + b"\xf6"
        for split in range(len(raw) + 1):
            decoder = validation.Decoder()
            messages = decoder.feed(raw[:split]) + decoder.feed(raw[split:])
            self.assertEqual(messages, [bytes(response)])
        with self.assertRaises(validation.UnsafeState):
            validation.Decoder().feed(b"x" * 4097)

    def test_configuration_rejects_unsafe_profiles_targets_and_limits(self):
        for changes in (
            {"host": "example.invalid"},
            {"host": "8.8.8.8"},
            {"delta": 6},
            {"delta": 0},
            {"delta": True},
            {"channel_index": 6},
            {"channel_index": True},
            {"schema_version": True},
            {"maximum_excursion_seconds": 30},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validation.Configuration.parse({**config_data(), **changes}, simulation=True)
        with self.assertRaises(ValueError):
            validation.Configuration.parse({**config_data(), "host": "10.0.0.8", "port": 22})
        with self.assertRaises(validation.UnsafeState):
            validation.mode_frame(8)

    def test_private_configuration_and_reports_reject_exposure_and_old_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            report = root / "report.json"
            sink = validation.PrivateReport(report)
            sink({"status": "RUNNING"})
            sink({"status": "PASS"})
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(report.read_text()), {"status": "PASS"})
            with self.assertRaises(ValueError):
                validation.PrivateReport(report)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                validation.PrivateReport(root / "other.json")


class LoopbackDevice:
    def __init__(self):
        self.lock = threading.Lock()
        self.observed = []
        self.state = {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)}
        self.first_channel = threading.Event()
        self.restore_channel = threading.Event()
        self.response_filter = None
        self.connection_response_filter = None
        self.connections = 0
        self.ignore_writes = False
        device = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                data = bytearray()
                with device.lock:
                    device.connections += 1
                    connection = device.connections
                try:
                    while True:
                        chunk = self.request.recv(1024)
                        if not chunk:
                            return
                        data.extend(chunk)
                        while len(data) >= 20:
                            command = bytes(data[:20])
                            del data[:20]
                            with device.lock:
                                device.observed.append(command)
                                if command == validation.SYSTEM_QUERY:
                                    response = system_reply(device.state["mode"])
                                elif command == validation.CHANNEL_QUERY:
                                    response = channels_reply(
                                        device.state["channels"], operation=0xFA
                                    )
                                elif command[1:3] == b"\xe2\xfa":
                                    if not device.ignore_writes:
                                        device.state["channels"] = tuple(command[3:9])
                                    if device.first_channel.is_set():
                                        device.restore_channel.set()
                                    else:
                                        device.first_channel.set()
                                    response = command
                                elif command[1:4] == b"\xe1\xfa\xdb":
                                    if not device.ignore_writes:
                                        device.state["mode"] = command[4]
                                    response = command + b"\xf5"
                                else:
                                    raise AssertionError("unexpected request")
                                if device.response_filter is not None:
                                    response = device.response_filter(command, response)
                                if device.connection_response_filter is not None:
                                    response = device.connection_response_filter(
                                        connection, command, response
                                    )
                            if response is None:
                                return
                            self.request.sendall(response[:7])
                            self.request.sendall(response[7:])
                except (ConnectionError, socket.timeout):
                    return

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    @property
    def port(self):
        return self.server.server_address[1]


class NativeWorkerLoopbackTests(unittest.TestCase):
    def test_lost_cleanup_barrier_reply_confirms_fresh_state_without_write_replay(self):
        for failed_connection, ignore_restore in ((3, False), (4, False), (3, True)):
            with self.subTest(failed_connection=failed_connection, ignore_restore=ignore_restore):
                with LoopbackDevice() as device:
                    queries = {}

                    def lost_barrier(connection, command, response):
                        if (
                            connection == 3
                            and command == validation.CHANNEL_QUERY
                            and ignore_restore
                        ):
                            device.ignore_writes = True
                        if command == validation.SYSTEM_QUERY:
                            queries[connection] = queries.get(connection, 0) + 1
                            if connection == failed_connection and queries[connection] == 2:
                                return b""
                        return response

                    device.connection_response_filter = lost_barrier
                    config = validation.Configuration.parse(
                        {**config_data(), "port": device.port}, simulation=True
                    )
                    result = validation.ValidationWorker(config).run()
                self.assertEqual(result["recovery"], "FAIL" if ignore_restore else "PASS", result)
                self.assertLess(result["excursion_seconds"], 10)
                writes = [command for command in device.observed if command[2] == 0xFA]
                self.assertEqual(len(writes), 4 if ignore_restore else 5)
                self.assertEqual(device.state["mode"], 1 if ignore_restore else 0)
                self.assertEqual(
                    device.state["channels"], (9 if ignore_restore else 10, 20, 30, 40, 50, 60)
                )
                failures = [
                    event
                    for event in result["events"]
                    if event["stage"].endswith("_system_barrier_transport_failed")
                ]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["phase"], "system_query_reply")

    def test_transient_guard_eof_timeout_and_restore_readback_loss_retry_only_reads(self):
        for failed_connection, failure in ((3, "eof"), (3, "timeout"), (4, "eof"), (5, "eof")):
            with self.subTest(failed_connection=failed_connection, failure=failure):
                with LoopbackDevice() as device:
                    device.connection_response_filter = lambda connection, command, response: (
                        (None if failure == "eof" else b"")
                        if connection == failed_connection
                        else response
                    )
                    config = validation.Configuration.parse(
                        {**config_data(), "port": device.port}, simulation=True
                    )
                    result = validation.ValidationWorker(config).run()
                self.assertEqual(result["status"], "PASS", result)
                self.assertLess(result["excursion_seconds"], 10)
                self.assertEqual(device.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
                self.assertEqual(
                    len([command for command in device.observed if command[2] == 0xFA]), 5
                )
                failures = [
                    event
                    for event in result["events"]
                    if event["stage"].endswith("_read_transport_failed")
                ]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["phase"], "system_query_reply")
                self.assertEqual(
                    failures[0]["reason"],
                    "EOFError" if failure == "eof" else socket.timeout.__name__,
                )

    def test_transient_connection_failure_then_native_fresh_read_restores(self):
        with LoopbackDevice() as device:
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )
            attempts = 0

            def factory(config, deadline, clock):
                nonlocal attempts
                attempts += 1
                if attempts == 3:
                    raise ConnectionRefusedError("synthetic one-off connection refusal")
                return validation.WireSession(config, deadline, clock)

            result = validation.ValidationWorker(config, session_factory=factory).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertLess(result["excursion_seconds"], 10)
        self.assertEqual(device.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
        self.assertEqual(len([command for command in device.observed if command[2] == 0xFA]), 5)
        failure = next(
            event
            for event in result["events"]
            if event["stage"] == "recovery_guard_read_transport_failed"
        )
        self.assertEqual(failure["phase"], "connect")

    def test_persistent_native_transport_loss_is_bounded_and_never_writes_blindly(self):
        with LoopbackDevice() as device:
            device.connection_response_filter = (
                lambda connection, command, response: None if connection >= 3 else response
            )
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )
            result = validation.ValidationWorker(config).run()
        self.assertEqual(result["experiment"], "PASS")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertLess(result["excursion_seconds"], 10)
        self.assertEqual(len([command for command in device.observed if command[2] == 0xFA]), 2)
        failures = [
            event
            for event in result["events"]
            if event["stage"] == "recovery_guard_read_transport_failed"
        ]
        self.assertEqual(len(failures), 3)
        self.assertEqual(device.connections, 5)

    def test_partial_reply_or_invalid_profile_is_terminal_without_native_retry(self):
        for failure in ("partial", "profile", "competing_mode"):
            with self.subTest(failure=failure):
                with LoopbackDevice() as device:

                    def corrupt(connection, command, response):
                        if connection != 3:
                            return response
                        if failure == "partial":
                            return b"\xf1"
                        if command == validation.CHANNEL_QUERY:
                            return None
                        raw = bytearray(response)
                        if failure == "profile":
                            raw[7] = 9
                        else:
                            raw[4] = 0
                        return bytes(raw)

                    device.connection_response_filter = corrupt
                    config = validation.Configuration.parse(
                        {**config_data(), "port": device.port}, simulation=True
                    )
                    result = validation.ValidationWorker(config).run()
                self.assertEqual(result["recovery"], "FAIL", result)
                self.assertEqual(device.connections, 3)
                self.assertEqual(
                    len([command for command in device.observed if command[2] == 0xFA]), 2
                )
                self.assertEqual(
                    next(
                        event
                        for event in result["events"]
                        if event["stage"] == "recovery_unconfirmed"
                    )["reason"],
                    "UnsafeState",
                )

    def test_full_native_experiment_timeout_and_first_recovery_loss_restore_in_time(self):
        with LoopbackDevice() as device:
            device.connection_response_filter = (
                lambda connection, command, response: None if connection == 2 else response
            )
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )

            class SlowExperiment(validation.ValidationWorker):
                def _command(self, channels, mode, deadline, stage):
                    if stage == "experiment":
                        self.session.send(
                            validation.channel_frame(channels, self.config.controller), deadline
                        )
                        self.session.send(validation.mode_frame(mode), deadline)
                        time.sleep(max(0, deadline - self.clock()))
                        raise validation.DeadlineError("synthetic full experiment timeout")
                    return super()._command(channels, mode, deadline, stage)

            result = SlowExperiment(config).run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS", result)
        self.assertLess(result["excursion_seconds"], 10)
        self.assertEqual(device.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})

    def test_whole_worker_with_native_tcp_fragmented_replies_and_write_echoes(self):
        with LoopbackDevice() as device:
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )
            result = validation.ValidationWorker(config).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertLess(result["excursion_seconds"], 10)
        self.assertEqual(device.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
        writes = [command for command in device.observed if command[2] == 0xFA]
        self.assertEqual(len(writes), 5)

    def test_valid_system_but_echoed_channel_query_never_establishes_false_zero_baseline(self):
        with LoopbackDevice() as device:
            device.response_filter = (
                lambda command, response: command
                if command == validation.CHANNEL_QUERY
                else response
            )
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )
            result = validation.ValidationWorker(config).run()
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(result["recovery"], "NOT_REQUIRED")
        self.assertFalse(any(command[2] == 0xFA for command in device.observed))

    def test_echoed_writes_and_acknowledgements_never_confirm_an_ignored_command(self):
        with LoopbackDevice() as device:
            device.ignore_writes = True
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port}, simulation=True
            )
            result = validation.ValidationWorker(config).run()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(len([command for command in device.observed if command[2] == 0xFA]), 2)

    def test_unambiguous_zero_fa_baseline_and_one_point_increase_are_reversible(self):
        with LoopbackDevice() as device:
            device.state["channels"] = (0, 0, 0, 0, 0, 0)
            config = validation.Configuration.parse(
                {**config_data(), "port": device.port, "delta": 1}, simulation=True
            )
            result = validation.ValidationWorker(config).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(device.state, {"mode": 0, "channels": (0, 0, 0, 0, 0, 0)})

    def test_detached_worker_restores_after_hangup_and_termination_during_cleanup(self):
        driver = """
import signal
import sys
from pathlib import Path
from tests.test_aquarius_validation import config_data
from tooling import aquarius_validation as v
config = v.Configuration.parse({**config_data(), 'port': int(sys.argv[1])}, simulation=True)
worker = v.ValidationWorker(config, sink=v.PrivateReport(Path(sys.argv[2])))
for name in ('SIGHUP', 'SIGTERM', 'SIGINT'):
    signal.signal(getattr(signal, name), worker.request_stop)
result = worker.run()
sys.exit(0 if result['recovery'] == 'PASS' else 1)
"""
        with tempfile.TemporaryDirectory() as temporary, LoopbackDevice() as device:
            root = Path(temporary)
            root.chmod(0o700)
            report = root / "detached-report.json"
            process = subprocess.Popen(
                [sys.executable, "-c", driver, str(device.port), str(report)],
                cwd=Path(__file__).resolve().parents[1],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                self.assertEqual(os.getsid(process.pid), process.pid)
                self.assertTrue(
                    device.first_channel.wait(3), "worker never sent its bounded change"
                )
                os.kill(process.pid, signal.SIGHUP)
                self.assertTrue(device.restore_channel.wait(3), "local finally cleanup did not run")
                os.kill(process.pid, signal.SIGTERM)
                self.assertEqual(process.wait(timeout=8), 0)
                result = json.loads(report.read_text())
                self.assertTrue(result["interrupted"])
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["recovery"], "PASS")
                self.assertLess(result["excursion_seconds"], 10)
                self.assertEqual(device.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()

"""Synthetic Task 004 optical windows and Automatic-only Shutdown recovery."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.aquarius_tcp_helpers import protocol, system_reply
from tests.test_aquarius_ha_validation import ExclusiveLoopbackDevice
from tests.test_aquarius_validation import LoopbackDevice, Simulator, config_data
from tooling import aquarius_task004_validation as task
from tooling import aquarius_validation as base


def task_data(action="optical"):
    device = config_data()
    if action in ("shutdown_automatic", "shutdown_manual"):
        device["delta"] = 0
        return {"schema_version": 1, "action": action, "device": device}
    return {
        "schema_version": 1,
        "action": action,
        "device": device,
        "sample_seconds": 2.0,
        "maximum_sample_percentage": 20,
    }


def simulate(action="optical", *, simulator=None, data=None, sleeper=None, sink=None):
    simulator = simulator or Simulator()
    config = task.Configuration.parse(data or task_data(action), simulation=True)
    worker_type = (
        task.OpticalValidationWorker if action == "optical" else task.ShutdownValidationWorker
    )
    worker = worker_type(
        config,
        session_factory=simulator.factory,
        clock=simulator.clock,
        sleeper=sleeper or simulator.clock.sleep,
        sink=sink,
    )
    simulator.worker = worker
    return worker.run(), simulator


def writes(simulator):
    return [command for _, command in simulator.writes]


class OpticalWindowTests(unittest.TestCase):
    def test_full_two_second_sample_and_exact_restoration_for_both_original_modes(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                simulator = Simulator()
                simulator.state = simulator.original = replace(simulator.state, mode=mode)
                result, simulator = simulate(simulator=simulator)
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(result["optical_observation"], "NOT_MEASURED")
                events = {event["stage"]: event for event in result["events"]}
                start = events["optical_sample_started"]["monotonic_seconds"]
                end = events["optical_sample_finished"]["monotonic_seconds"]
                self.assertAlmostEqual(end - start, 2.0)
                self.assertLess(events["optical_sample_finished"]["excursion_seconds"], 3.0)
                self.assertGreater(events["recovery_guard_confirmed"]["monotonic_seconds"], end)
                self.assertLess(result["excursion_seconds"], 10)
                self.assertEqual(len(writes(simulator)), 5 if mode == 0 else 4)

    def test_each_channel_changes_only_its_requested_small_percentage(self):
        for index in range(6):
            with self.subTest(channel=index):
                simulator = Simulator()
                simulator.state = simulator.original = replace(simulator.state, channels=(10,) * 6)
                data = task_data()
                data["device"].update(channel_index=index, delta=1)
                result, simulator = simulate(simulator=simulator, data=data)
                self.assertEqual(result["status"], "PASS", result)
                changed = list(simulator.original.channels)
                changed[index] += 1
                self.assertEqual(writes(simulator)[0], base.channel_frame(changed, (18, 60)))
                self.assertEqual(simulator.state, simulator.original)

    def test_high_or_zero_sample_output_is_rejected_before_any_write(self):
        for start, delta in ((22, -1), (1, -1)):
            simulator = Simulator()
            simulator.state = simulator.original = replace(
                simulator.state, channels=(start, 20, 30, 40, 50, 60)
            )
            data = task_data()
            data["device"]["delta"] = delta
            result, simulator = simulate(simulator=simulator, data=data)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(writes(simulator), [])
            self.assertEqual(simulator.state, simulator.original)

    def test_late_confirmation_skips_sample_and_preserves_cleanup_reserve(self):
        simulator = Simulator()

        def delayed_confirmation(event, sim):
            if event == "read" and sim.worker.excursion_started is not None:
                sim.hook = None
                sim.clock.advance(0.5, sim.worker.excursion_started + 3)

        simulator.hook = delayed_confirmation
        result, simulator = simulate(simulator=simulator)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertNotIn("optical_sample_started", [event["stage"] for event in result["events"]])
        self.assertLess(result["excursion_seconds"], 10)

    def test_signal_during_sample_restores_early(self):
        simulator = Simulator()

        def stop_during_hold(seconds):
            simulator.clock.sleep(seconds)
            simulator.worker.request_stop()

        result, simulator = simulate(simulator=simulator, sleeper=stop_during_hold)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], 4)

    def test_competing_change_during_sample_is_never_overwritten(self):
        simulator = Simulator()

        def compete(seconds):
            simulator.clock.sleep(seconds)
            simulator.state = replace(simulator.state, channels=(9, 20, 31, 40, 50, 60))

        result, simulator = simulate(simulator=simulator, sleeper=compete)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(writes(simulator)), 2)
        self.assertEqual(simulator.state.channels[2], 31)

    def test_evidence_io_is_deferred_through_the_sample_and_recovery(self):
        simulator = Simulator()
        persisted = []

        def sink(report):
            if simulator.worker.excursion_started is not None:
                self.assertEqual(report["events"][-1]["stage"], "finished")
                self.assertEqual(simulator.state, simulator.original)
            persisted.append(json.loads(json.dumps(report)))

        result, simulator = simulate(simulator=simulator, sink=sink)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(
            any(item["events"][-1]["stage"] == "experiment_intent" for item in persisted[:-1])
        )


class ShutdownTransactionTests(unittest.TestCase):
    def test_initial_all_zero_baseline_does_not_prove_channel_retention(self):
        simulator = Simulator()
        simulator.state = simulator.original = replace(simulator.state, channels=(0,) * 6)
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["status"], "PASS")
        observed = next(e for e in result["events"] if e["stage"] == "experiment_confirmed")
        self.assertEqual(observed["channel_observation"], "all_zero_baseline_ambiguous")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])

    def test_uncertain_shutdown_delivery_or_reply_restores_only_after_fresh_guard(self):
        for failure in ("mode_sent", "system"):
            simulator = Simulator()

            def fail_once(event, sim):
                if event == failure and sim.state.mode == 8:
                    sim.hook = None
                    raise ConnectionResetError("synthetic uncertain Shutdown response")

            simulator.hook = fail_once
            result, simulator = simulate("shutdown_automatic", simulator=simulator)
            self.assertEqual(result["experiment"], "FAIL")
            self.assertEqual(result["recovery"], "PASS")
            self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])
            self.assertEqual(simulator.state.mode, 0)

    def test_change_during_intent_persistence_prevents_shutdown(self):
        simulator = Simulator()

        def sink(report):
            if report["events"][-1]["stage"] == "experiment_intent":
                simulator.state = replace(simulator.state, channels=(11, 20, 30, 40, 50, 60))

        result, simulator = simulate("shutdown_automatic", simulator=simulator, sink=sink)
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(result["recovery"], "NOT_REQUIRED")
        self.assertEqual(writes(simulator), [])

    def test_retained_and_zero_shutdown_responses_restore_only_automatic(self):
        for zero in (False, True):
            with self.subTest(zero=zero):
                simulator = Simulator()

                def program(event, sim):
                    if event == "mode_sent":
                        if sim.state.mode == 8 and zero:
                            sim.state = replace(sim.state, channels=(0,) * 6)
                        elif sim.state.mode == 0:
                            # Resuming a running program may produce a newer vector.
                            sim.state = replace(sim.state, channels=(11, 20, 30, 40, 50, 60))

                simulator.hook = program
                result, simulator = simulate("shutdown_automatic", simulator=simulator)
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])
                self.assertEqual(simulator.state.mode, 0)
                self.assertLess(result["excursion_seconds"], 10)
                observation = next(
                    event for event in result["events"] if event["stage"] == "experiment_confirmed"
                )
                self.assertEqual(
                    observation["channel_observation"], "all_zero" if zero else "retained"
                )
                restored = next(
                    event for event in result["events"] if event["stage"] == "recovery_confirmed"
                )
                self.assertFalse(restored["original_channels_match"])

    def test_manual_shutdown_and_unknown_origins_never_send_a_command(self):
        for mode in (1, 8, 17):
            simulator = Simulator()
            simulator.state = simulator.original = replace(simulator.state, mode=mode)
            result, simulator = simulate("shutdown_automatic", simulator=simulator)
            self.assertEqual(result["experiment"], "NOT_TESTED")
            self.assertEqual(result["recovery"], "NOT_REQUIRED")
            self.assertEqual(writes(simulator), [])

    def test_unstable_baseline_never_sends_a_command(self):
        simulator = Simulator()
        calls = 0

        def drift(event, sim):
            nonlocal calls
            if event == "read":
                calls += 1
                if calls == 2:
                    sim.state = replace(sim.state, channels=(11, 20, 30, 40, 50, 60))

        simulator.hook = drift
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(writes(simulator), [])

    def test_mixed_shutdown_vector_is_not_trusted_or_overwritten(self):
        simulator = Simulator()

        def mixed(event, sim):
            if event == "mode_sent" and sim.state.mode == 8:
                sim.state = replace(sim.state, channels=(0, 20, 30, 40, 50, 60))

        simulator.hook = mixed
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8)])

    def test_competing_mode_or_vector_after_confirmed_shutdown_stops_cleanup(self):
        for change in ({"mode": 1}, {"channels": (0,) * 6}, {"controller": (99, 99)}):
            simulator = Simulator()

            def competing(event, sim):
                if event == "read" and sim.worker.cleaning:
                    sim.state = replace(sim.state, **change)

            simulator.hook = competing
            result, simulator = simulate("shutdown_automatic", simulator=simulator)
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(writes(simulator), [protocol.mode_frame(8)])

    def test_transient_recovery_read_failure_retries_only_status(self):
        simulator = Simulator()
        failed = False

        def fail_once(event, sim):
            nonlocal failed
            if event == "read" and sim.worker.cleaning and not failed:
                failed = True
                raise TimeoutError("synthetic guard timeout")

        simulator.hook = fail_once
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(failed)
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])

    def test_signal_after_shutdown_delivery_still_restores_automatic(self):
        simulator = Simulator()

        def stop(event, sim):
            if event == "mode_sent" and sim.state.mode == 8:
                sim.worker.request_stop()

        simulator.hook = stop
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertTrue(result["interrupted"])
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])

    def test_lost_restore_barrier_only_retries_fresh_readback(self):
        simulator = Simulator()

        def lost(event, sim):
            if event == "system" and sim.worker.cleaning:
                raise EOFError("synthetic lost Automatic barrier")

        simulator.hook = lost
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(0)])

    def test_persistent_recovery_loss_stays_bounded_without_blind_restore(self):
        simulator = Simulator()

        def lost(event, sim):
            if event == "read" and sim.worker.cleaning:
                raise TimeoutError("synthetic persistent outage")

        simulator.hook = lost
        result, simulator = simulate("shutdown_automatic", simulator=simulator)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8)])
        self.assertLess(result["excursion_seconds"], 10)


class ManualShutdownTests(unittest.TestCase):
    def manual_simulator(self, *, zero=False):
        simulator = Simulator()
        simulator.state = simulator.original = replace(simulator.state, mode=1)

        def shutdown_zero(event, sim):
            if zero and event == "mode_sent" and sim.state.mode == 8:
                sim.state = replace(sim.state, channels=(0,) * 6)

        simulator.hook = shutdown_zero
        return simulator

    def test_retained_manual_snapshot_requires_only_mode_commands(self):
        simulator = self.manual_simulator()
        result, simulator = simulate("shutdown_manual", simulator=simulator)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(1)])
        self.assertEqual(simulator.state, simulator.original)
        self.assertFalse(result["channel_writes_permitted"])

    def test_shutdown_zero_and_confirmed_manual_zero_allow_one_guarded_snapshot_restore(self):
        simulator = self.manual_simulator(zero=True)
        result, simulator = simulate("shutdown_manual", simulator=simulator)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(
            writes(simulator),
            [
                protocol.mode_frame(8),
                base.mode_frame(1),
                base.channel_frame(simulator.original.channels, simulator.original.controller),
                base.mode_frame(1),
            ],
        )
        self.assertEqual(
            result["channel_restoration_path"], "confirmed_shutdown_zero_then_manual_zero"
        )
        self.assertTrue(result["channel_writes_permitted"])
        self.assertLess(result["excursion_seconds"], 10)
        stages = [event["stage"] for event in result["events"]]
        self.assertLess(
            stages.index("restore_original_mode_system_barrier_confirmed"),
            stages.index("manual_zero_restore_guard_confirmed"),
        )
        self.assertLess(
            stages.index("manual_zero_restore_guard_confirmed"),
            stages.index("restore_manual_channels_channels_send"),
        )

    def test_retained_shutdown_then_zero_manual_is_not_snapshot_restore_authority(self):
        simulator = self.manual_simulator()

        def unexpected_zero(event, sim):
            if event == "mode_sent" and sim.state.mode == 1:
                sim.state = replace(sim.state, channels=(0,) * 6)

        simulator.hook = unexpected_zero
        result, simulator = simulate("shutdown_manual", simulator=simulator)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(1)])
        self.assertFalse(result["channel_writes_permitted"])

    def test_lost_manual_barrier_does_not_permit_snapshot_restore_despite_later_zero_read(self):
        simulator = self.manual_simulator(zero=True)
        program = simulator.hook

        def lose_manual_barrier(event, sim):
            program(event, sim)
            if event == "system" and sim.worker.cleaning:
                raise EOFError("synthetic lost Manual processing barrier")

        simulator.hook = lose_manual_barrier
        result, simulator = simulate("shutdown_manual", simulator=simulator)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(1)])
        self.assertFalse(result["channel_writes_permitted"])

    def test_competing_zero_guard_mode_or_channels_prevents_original_vector_replay(self):
        for change in ({"mode": 0}, {"channels": (1, 0, 0, 0, 0, 0)}, {"controller": (77, 77)}):
            simulator = self.manual_simulator(zero=True)
            program = simulator.hook
            manual_reads = 0

            def compete(event, sim):
                nonlocal manual_reads
                program(event, sim)
                if event == "read" and sim.worker.cleaning and sim.state.mode == 1:
                    manual_reads += 1
                    if manual_reads == 2:
                        sim.state = replace(sim.state, **change)

            simulator.hook = compete
            result, simulator = simulate("shutdown_manual", simulator=simulator)
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(writes(simulator), [protocol.mode_frame(8), base.mode_frame(1)])
            self.assertFalse(result["channel_writes_permitted"])

    def test_manual_resume_preserves_three_second_snapshot_reserve(self):
        simulator = self.manual_simulator(zero=True)
        program = simulator.hook

        def spend_guard_budget(event, sim):
            program(event, sim)
            if event == "read" and sim.worker.cleaning:
                sim.clock.value = sim.worker.excursion_started + 4.71

        simulator.hook = spend_guard_budget
        result, simulator = simulate("shutdown_manual", simulator=simulator)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(writes(simulator), [protocol.mode_frame(8)])
        self.assertLess(result["excursion_seconds"], 10)

    def test_manual_request_never_changes_an_automatic_baseline(self):
        result, simulator = simulate("shutdown_manual")
        self.assertEqual(result["experiment"], "NOT_TESTED")
        self.assertEqual(writes(simulator), [])


class Task004NativeTests(unittest.TestCase):
    def test_transient_optical_profile_or_mode_contradiction_cannot_authorize_cleanup(self):
        for failure in ("profile", "automatic_then_eof"):
            with self.subTest(failure=failure), LoopbackDevice() as lamp:

                def contradictory(connection, command, response):
                    if connection != 3:
                        return response
                    if command == base.SYSTEM_QUERY:
                        if failure == "automatic_then_eof":
                            return system_reply(0)
                        changed = bytearray(response)
                        changed[9] = 99
                        return bytes(changed)
                    if command == base.CHANNEL_QUERY and failure == "automatic_then_eof":
                        return None
                    return response

                lamp.connection_response_filter = contradictory
                data = task_data()
                data["device"]["port"] = lamp.port
                result = task.OpticalValidationWorker(
                    task.Configuration.parse(data, simulation=True)
                ).run()
            self.assertEqual(result["experiment"], "FAIL")
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(lamp.connections, 4)
            self.assertEqual(len([c for c in lamp.observed if c[2] == 0xFA]), 2)
            self.assertNotIn(base.mode_frame(0), lamp.observed)

    def test_native_manual_retained_or_zero_restores_exact_snapshot_with_single_client(self):
        for zero in (False, True):
            with self.subTest(zero=zero), ExclusiveLoopbackDevice() as lamp:
                lamp.state["mode"] = 1
                original = dict(lamp.state)

                def shutdown_zero(command, response):
                    if zero and command == protocol.mode_frame(8):
                        lamp.state["channels"] = (0,) * 6
                    return response

                lamp.response_filter = shutdown_zero
                data = task_data("shutdown_manual")
                data["device"]["port"] = lamp.port
                result = task.ShutdownValidationWorker(
                    task.Configuration.parse(data, simulation=True)
                ).run()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(lamp.state, original)
            self.assertEqual(lamp.rejected_connections, 0)
            commands = [command for command in lamp.observed if command[2] == 0xFA]
            self.assertEqual(commands[:2], [protocol.mode_frame(8), base.mode_frame(1)])
            self.assertEqual(len(commands), 4 if zero else 2)
            self.assertNotIn(base.mode_frame(0), commands)
            self.assertLess(result["excursion_seconds"], 10)

    def test_lost_manual_fresh_confirmation_never_triggers_channel_replay(self):
        with LoopbackDevice() as lamp:
            lamp.state["mode"] = 1

            def lose_confirmation(connection, command, response):
                if command == protocol.mode_frame(8):
                    lamp.state["channels"] = (0,) * 6
                if connection >= 5:
                    return response[:7] if command == base.SYSTEM_QUERY else response
                return response

            lamp.connection_response_filter = lose_confirmation
            data = task_data("shutdown_manual")
            data["device"]["port"] = lamp.port
            result = task.ShutdownValidationWorker(
                task.Configuration.parse(data, simulation=True)
            ).run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(
            [command for command in lamp.observed if command[2] == 0xFA],
            [protocol.mode_frame(8), base.mode_frame(1)],
        )

    def test_native_shutdown_readback_and_automatic_resume_with_fragmented_echoes(self):
        for zero in (False, True):
            with self.subTest(zero=zero), ExclusiveLoopbackDevice() as lamp:

                def program(command, response):
                    if command == protocol.mode_frame(8) and zero:
                        lamp.state["channels"] = (0,) * 6
                    if command == base.mode_frame(0):
                        lamp.state["channels"] = (10, 20, 30, 40, 50, 60)
                    return response

                lamp.response_filter = program
                data = task_data("shutdown_automatic")
                data["device"]["port"] = lamp.port
                worker = task.ShutdownValidationWorker(
                    task.Configuration.parse(data, simulation=True)
                )
                result = worker.run()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(lamp.rejected_connections, 0)
            self.assertEqual(
                [command for command in lamp.observed if command[2] == 0xFA],
                [protocol.mode_frame(8), base.mode_frame(0)],
            )
            self.assertEqual(lamp.state["mode"], 0)
            self.assertLess(result["excursion_seconds"], 10)

    def test_native_optical_window_is_followed_by_exact_channel_recovery(self):
        with ExclusiveLoopbackDevice() as lamp:
            data = task_data()
            data["device"]["port"] = lamp.port
            result = task.OpticalValidationWorker(
                task.Configuration.parse(data, simulation=True)
            ).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(lamp.rejected_connections, 0)
        self.assertEqual(lamp.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
        self.assertLess(result["excursion_seconds"], 10)

    def test_shutdown_channel_query_echo_cannot_confirm_shutdown(self):
        with LoopbackDevice() as lamp:
            lamp.connection_response_filter = lambda connection, command, response: (
                command if connection >= 3 and command == base.CHANNEL_QUERY else response
            )
            data = task_data("shutdown_automatic")
            data["device"]["port"] = lamp.port
            result = task.ShutdownValidationWorker(
                task.Configuration.parse(data, simulation=True)
            ).run()
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(
            [command for command in lamp.observed if command[2] == 0xFA], [protocol.mode_frame(8)]
        )

    def test_one_unsafe_experiment_reply_cannot_be_forgotten_by_a_later_valid_guard(self):
        for failure in ("profile", "partial", "channel_echo", "manual_then_eof"):
            with self.subTest(failure=failure), LoopbackDevice() as lamp:

                def one_bad_observation(connection, command, response):
                    if connection != 3:
                        return response
                    if command == base.SYSTEM_QUERY:
                        if failure == "partial":
                            return response[:7]
                        if failure == "profile":
                            changed = bytearray(response)
                            changed[9] = 99
                            return bytes(changed)
                        if failure == "manual_then_eof":
                            return system_reply(1)
                    if command == base.CHANNEL_QUERY:
                        if failure == "channel_echo":
                            return command
                        if failure == "manual_then_eof":
                            return None
                    return response

                lamp.connection_response_filter = one_bad_observation
                data = task_data("shutdown_automatic")
                data["device"]["port"] = lamp.port
                result = task.ShutdownValidationWorker(
                    task.Configuration.parse(data, simulation=True)
                ).run()
            self.assertEqual(result["experiment"], "FAIL")
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(lamp.connections, 4)
            self.assertEqual(
                [command for command in lamp.observed if command[2] == 0xFA],
                [protocol.mode_frame(8)],
            )
            guard = next(e for e in result["events"] if e["stage"] == "recovery_guard_confirmed")
            self.assertEqual(guard["state"]["mode"], 8)

    def test_competing_manual_system_then_lost_channels_is_not_retried(self):
        with LoopbackDevice() as lamp:

            def contradictory(connection, command, response):
                if connection == 4:
                    return system_reply(1) if command == base.SYSTEM_QUERY else None
                return response

            lamp.connection_response_filter = contradictory
            data = task_data("shutdown_automatic")
            data["device"]["port"] = lamp.port
            result = task.ShutdownValidationWorker(
                task.Configuration.parse(data, simulation=True)
            ).run()
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(lamp.connections, 4)
        self.assertEqual(
            [command for command in lamp.observed if command[2] == 0xFA], [protocol.mode_frame(8)]
        )


class Task004ConfigurationTests(unittest.TestCase):
    def test_sample_limits_and_unapproved_shutdown_actions_fail_closed(self):
        for key, value in (
            ("sample_seconds", 2.01),
            ("sample_seconds", float("nan")),
            ("sample_seconds", True),
            ("maximum_sample_percentage", 21),
            ("maximum_sample_percentage", True),
            ("action", "shutdown_unknown"),
        ):
            data = task_data()
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                task.Configuration.parse(data, simulation=True)
        for delta in (1, -1, True):
            data = task_data("shutdown_automatic")
            data["device"]["delta"] = delta
            with self.assertRaises(ValueError):
                task.Configuration.parse(data, simulation=True)

    def test_private_configuration_permissions_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            data = task_data("shutdown_automatic")
            data["device"]["host"] = "10.0.0.8"
            path.write_text(json.dumps(data))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                task._configuration(path)
            path.chmod(0o600)
            self.assertEqual(task._configuration(path).action, "shutdown_automatic")
            link = Path(temporary) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                task._configuration(link)


if __name__ == "__main__":
    unittest.main()

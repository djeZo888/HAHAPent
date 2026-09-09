"""Synthetic fault matrix and exclusive-loopback proof for dark optical sampling."""

import json
import unittest
from dataclasses import replace

from tests.aquarius_tcp_helpers import protocol
from tests.test_aquarius_ha_validation import ExclusiveLoopbackDevice
from tests.test_aquarius_validation import Simulator, config_data
from tooling import aquarius_dark_optical_validation as dark
from tooling import aquarius_validation as base

ORIGINAL = (40, 0, 0, 0, 0, 0)


def configuration(channel=1):
    device = config_data()
    device.update(delta=0, channel_index=channel)
    return {
        "schema_version": 1,
        "action": "dark_optical",
        "device": device,
        "expected_manual_channels": list(ORIGINAL),
        "selected_percentage": 5,
        "sample_seconds": 0.3,
    }


def simulate(*, hook=None, sleeper=None, sink=None, data=None):
    simulator = Simulator()
    simulator.state = simulator.original = replace(simulator.state, mode=1, channels=ORIGINAL)

    def events(event, sim):
        if event == "mode_sent" and sim.state.mode == 8:
            sim.state = replace(sim.state, channels=dark.ZERO)
        if hook:
            hook(event, sim)

    simulator.hook = events
    worker = dark.DarkOpticalWorker(
        dark.Configuration.parse(data or configuration(), simulation=True),
        session_factory=simulator.factory,
        clock=simulator.clock,
        sleeper=sleeper or simulator.clock.sleep,
        sink=sink,
    )
    simulator.worker = worker
    return worker.run(), simulator


def commands(simulator):
    return [command for _, command in simulator.writes]


class DarkCompositeTests(unittest.TestCase):
    def test_each_single_channel_is_sampled_from_zero_then_exact_manual_restored(self):
        for channel in range(6):
            result, simulator = simulate(data=configuration(channel))
            with self.subTest(channel=channel):
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(result["sample_window"], "COMPLETED")
                self.assertEqual(result["optical_observation"], "NOT_MEASURED")
                self.assertEqual(simulator.state, simulator.original)
                selected = [0] * 6
                selected[channel] = 5
                self.assertEqual(
                    commands(simulator),
                    [
                        protocol.mode_frame(8),
                        base.mode_frame(1),
                        base.channel_frame(selected, simulator.state.controller),
                        base.mode_frame(1),
                        base.channel_frame(ORIGINAL, simulator.state.controller),
                        base.mode_frame(1),
                    ],
                )
                stages = {event["stage"]: event for event in result["events"]}
                self.assertLessEqual(stages["optical_sample_finished"]["excursion_seconds"], 4)
                self.assertLess(stages["manual_zero_guard_confirmed"]["excursion_seconds"], 2.2)
                self.assertLess(result["excursion_seconds"], 5)
                self.assertEqual(result["recovery_reserved_seconds"], 5.5)

    def test_baseline_and_final_prewrite_guard_must_match_exact_declared_manual(self):
        for mutate in ("read", "intent"):

            def change(event, sim):
                if mutate == "read" and event == "read":
                    sim.state = replace(sim.state, channels=(41, 0, 0, 0, 0, 0))

            def sink(report):
                if mutate == "intent" and report["events"][-1]["stage"] == "experiment_intent":
                    raise OSError("synthetic durable-intent failure")

            result, simulator = simulate(hook=change, sink=sink)
            self.assertEqual(result["experiment"], "NOT_TESTED")
            self.assertEqual(commands(simulator), [])

    def test_late_manual_preparation_skips_selected_command_and_restores_from_zero(self):
        delayed = False

        def delay(event, sim):
            nonlocal delayed
            if not delayed and event == "read" and sim.worker.phase == "manual":
                delayed = True
                sim.clock.advance(0.5, sim.worker.excursion_started + 4)

        result, simulator = simulate(hook=delay)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS", result)
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(
            commands(simulator),
            [
                protocol.mode_frame(8),
                base.mode_frame(1),
                base.channel_frame(ORIGINAL, simulator.state.controller),
                base.mode_frame(1),
            ],
        )
        self.assertNotIn("optical_sample_started", [e["stage"] for e in result["events"]])

    def test_late_sample_readback_skips_hold_and_preserves_recovery_budget(self):
        delayed = False

        def delay(event, sim):
            nonlocal delayed
            if not delayed and event == "read" and sim.worker.phase == "sample":
                delayed = True
                sim.clock.advance(0.9, sim.worker.excursion_started + 4)

        result, simulator = simulate(hook=delay)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS", result)
        self.assertEqual(result["sample_window"], "SKIPPED_DEADLINE")
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], 6)

    def test_stop_at_each_complete_preparation_or_sample_boundary_restores_once(self):
        for stopped_phase in ("off", "manual", "sample"):
            stopped = False

            def stop(event, sim):
                nonlocal stopped
                if not stopped and event == "mode_sent" and sim.worker.phase == stopped_phase:
                    stopped = True
                    sim.worker.request_stop()

            result, simulator = simulate(hook=stop)
            with self.subTest(phase=stopped_phase):
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["recovery"], "PASS", result)
                self.assertTrue(result["interrupted"])
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(
                    commands(simulator).count(
                        base.channel_frame(ORIGINAL, simulator.state.controller)
                    ),
                    1,
                )

    def test_one_time_transport_failure_after_barrier_recovers_without_command_retry(self):
        for phase in ("off", "manual", "sample"):
            failed = False

            def fail(event, sim):
                nonlocal failed
                if not failed and event == "read" and sim.worker.phase == phase:
                    failed = True
                    raise TimeoutError("synthetic independent read failure")

            result, simulator = simulate(hook=fail)
            with self.subTest(phase=phase):
                self.assertEqual(result["experiment"], "FAIL")
                self.assertEqual(result["recovery"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertEqual(commands(simulator).count(protocol.mode_frame(8)), 1)

    def test_lost_queried_barrier_recovers_only_after_exact_pending_target_is_read(self):
        for phase in ("off", "manual", "sample"):
            failed = False

            def fail(event, sim):
                nonlocal failed
                if not failed and event == "system" and sim.worker.phase == phase:
                    failed = True
                    raise TimeoutError("synthetic lost processing reply")

            result, simulator = simulate(hook=fail)
            with self.subTest(phase=phase):
                self.assertEqual(result["experiment"], "FAIL")
                self.assertEqual(result["recovery"], "PASS", result)
                self.assertEqual(simulator.state, simulator.original)
                self.assertIn(
                    "pending_processing_freshly_confirmed", [e["stage"] for e in result["events"]]
                )

    def test_uncertain_barrier_with_original_state_is_not_falsely_confirmed(self):
        failed = False

        def fail(event, sim):
            nonlocal failed
            if not failed and event == "system" and sim.worker.phase == "off":
                failed = True
                sim.state = sim.original
                raise TimeoutError("synthetic ignored Off and lost reply")

        result, simulator = simulate(hook=fail)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(commands(simulator), [protocol.mode_frame(8)])

    def test_send_quarantine_partial_or_competing_observation_never_authorizes_replay(self):
        for failure in ("send", "quarantine", "partial", "mode", "channels", "profile"):
            failed = False

            def fail(event, sim):
                nonlocal failed
                if failed or sim.worker.phase != "off":
                    return
                if failure == "send" and event == "mode_sent":
                    failed = True
                    raise OSError("synthetic interrupted send")
                if failure == "quarantine" and event == "quarantine":
                    failed = True
                    raise TimeoutError("synthetic interrupted quarantine")
                if failure == "partial" and event == "system":
                    failed = True
                    raise base.UnsafeState("synthetic partial reply")
                if event == "read" and failure in ("mode", "channels", "profile"):
                    failed = True
                    sim.state = replace(
                        sim.state,
                        **{
                            "mode": {"mode": 0},
                            "channels": {"channels": (1, 0, 0, 0, 0, 0)},
                            "profile": {"version": (2, 6)},
                        }[failure],
                    )

            result, simulator = simulate(hook=fail)
            with self.subTest(failure=failure):
                self.assertEqual(result["recovery"], "FAIL")
                self.assertEqual(commands(simulator), [protocol.mode_frame(8)])

    def test_competing_change_after_verified_sample_is_preserved(self):
        def change(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.state = replace(sim.state, channels=(0, 5, 1, 0, 0, 0))

        result, simulator = simulate(hook=change)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(commands(simulator)), 4)
        self.assertEqual(simulator.state.channels, (0, 5, 1, 0, 0, 0))

    def test_future_sample_vector_is_competing_until_a_sample_command_was_sent(self):
        failed = False

        def compete(event, sim):
            nonlocal failed
            if not failed and event == "read" and sim.worker.phase == "manual":
                failed = True
                sim.state = replace(sim.state, channels=sim.worker.changed)
                raise TimeoutError("synthetic incomplete read before any sample command")

        result, simulator = simulate(hook=compete)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(commands(simulator), [protocol.mode_frame(8), base.mode_frame(1)])
        self.assertEqual(simulator.state.channels, (0, 5, 0, 0, 0, 0))

    def test_transient_contradiction_is_not_forgotten_by_later_owned_looking_read(self):
        for changed in ({"mode": 0}, {"version": (2, 6)}):
            observed = False

            def transient(event, sim):
                nonlocal observed
                if event == "read" and sim.worker.phase == "off":
                    if not observed:
                        observed = True
                        sim.state = replace(sim.state, **changed)
                    elif sim.worker.cleaning:
                        sim.state = replace(sim.original, mode=8, channels=dark.ZERO)

            result, simulator = simulate(hook=transient)
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(commands(simulator), [protocol.mode_frame(8)])

    def test_all_zero_original_is_not_reported_as_channel_retention(self):
        data = configuration()
        data["expected_manual_channels"] = [0] * 6

        def zero_initial(event, sim):
            if sim.worker.excursion_started is None:
                sim.state = sim.original = replace(sim.state, channels=dark.ZERO)

        result, simulator = simulate(hook=zero_initial, data=data)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(simulator.state.channels, dark.ZERO)
        self.assertNotIn("retention", json.dumps(result))

    def test_recovery_read_failures_consume_read_budget_without_repeating_any_write(self):
        failures = 0

        def fail(event, sim):
            nonlocal failures
            if event == "read" and sim.worker.cleaning and failures < 2:
                failures += 1
                # A complete 0.8-second transport timeout, including the fake
                # reader's first 0.4 seconds, must fit the real reserve policy.
                sim.clock.advance(0.4, sim.worker.session.read_deadline)
                raise TimeoutError("synthetic transient guard timeout")

        result, simulator = simulate(hook=fail)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(failures, 2)
        self.assertEqual(simulator.state, simulator.original)
        self.assertLess(result["excursion_seconds"], 9.5)
        self.assertEqual(len(commands(simulator)), 6)

    def test_exhausted_recovery_reads_stop_before_spending_four_second_command_reserve(self):
        def fail(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.clock.advance(0.4, sim.worker.session.read_deadline)
                raise TimeoutError("synthetic repeated guard timeout")

        result, simulator = simulate(hook=fail)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(len(commands(simulator)), 4)
        self.assertLessEqual(result["excursion_seconds"], 5.5)

    def test_recovery_write_or_interrupted_quarantine_is_never_repeated(self):
        for failure in ("channel_sent", "quarantine"):
            failed = False

            def fail(event, sim):
                nonlocal failed
                if not failed and sim.worker.phase == "restore_original" and event == failure:
                    failed = True
                    raise OSError("synthetic cleanup transport failure")

            result, simulator = simulate(hook=fail)
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(
                commands(simulator).count(base.channel_frame(ORIGINAL, simulator.state.controller)),
                1,
            )

    def test_recovery_barrier_timeout_can_be_confirmed_by_fresh_exact_original(self):
        failed = False

        def fail(event, sim):
            nonlocal failed
            if not failed and event == "system" and sim.worker.phase == "restore_original":
                failed = True
                raise TimeoutError("synthetic lost cleanup barrier")

        result, simulator = simulate(hook=fail)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(len(commands(simulator)), 6)

    def test_reporting_io_occurs_only_before_excursion_or_after_restoration(self):
        calls = []

        def sink(report):
            if "excursion_seconds" in report["events"][-1]:
                self.assertEqual(report["events"][-1]["stage"], "finished")
            calls.append(json.loads(json.dumps(report)))

        result, simulator = simulate(sink=sink)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(any(e["events"][-1]["stage"] == "experiment_intent" for e in calls))
        self.assertEqual(simulator.state, simulator.original)


class NativeExclusiveTests(unittest.TestCase):
    def run_native(self, *, filter_factory=None):
        with ExclusiveLoopbackDevice() as lamp:
            lamp.state = {"mode": 1, "channels": ORIGINAL}
            special = filter_factory(lamp) if filter_factory else None

            def response(command, reply):
                if command == protocol.mode_frame(8):
                    lamp.state["channels"] = dark.ZERO
                return special(command, reply) if special else reply

            lamp.response_filter = response
            data = configuration()
            data["device"]["port"] = lamp.server.server_address[1]
            result = dark.DarkOpticalWorker(dark.Configuration.parse(data, simulation=True)).run()
        return result, lamp

    def test_actual_exclusive_tcp_full_sequence_echoes_zero_readback_and_restore(self):
        result, lamp = self.run_native()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(lamp.state, {"mode": 1, "channels": ORIGINAL})
        self.assertEqual(lamp.rejected_connections, 0)
        self.assertEqual(len([command for command in lamp.observed if command[2] == 0xFA]), 6)
        self.assertLess(result["excursion_seconds"], 9.5)

    def test_actual_lost_off_barrier_uses_fresh_owned_guard_then_exact_manual_restore(self):
        def filter_factory(lamp):
            failed = False

            def response(command, reply):
                nonlocal failed
                if not failed and command == base.SYSTEM_QUERY and lamp.state["mode"] == 8:
                    failed = True
                    return None
                return reply

            return response

        result, lamp = self.run_native(filter_factory=filter_factory)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS", result)
        self.assertEqual(lamp.state, {"mode": 1, "channels": ORIGINAL})
        self.assertEqual(lamp.rejected_connections, 0)


class ConfigurationTests(unittest.TestCase):
    def test_limits_and_shape_are_strict(self):
        for key, value in (
            ("selected_percentage", 0),
            ("selected_percentage", 6),
            ("selected_percentage", True),
            ("sample_seconds", 0),
            ("sample_seconds", 0.31),
            ("sample_seconds", float("nan")),
            ("schema_version", True),
            ("action", "automatic"),
        ):
            raw = configuration()
            raw[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                dark.Configuration.parse(raw, simulation=True)
        raw = configuration()
        raw["device"]["delta"] = 1
        with self.assertRaises(ValueError):
            dark.Configuration.parse(raw, simulation=True)


if __name__ == "__main__":
    unittest.main()

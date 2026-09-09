"""Synthetic native-service transactions and independent loopback TCP cleanup."""

import contextlib
import io
import json
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.aquarius_tcp_helpers import protocol
from tests.test_aquarius_ha_validation import TOKEN, ExclusiveLoopbackDevice, FakeHA
from tests.test_aquarius_validation import Simulator, config_data
from tooling import aquarius_task004_ha_service as service
from tooling import aquarius_task004_ha_validation as ha
from tooling import aquarius_task004_validation as direct
from tooling import aquarius_validation as base


def config_data_ha(action="power_manual", channel=0):
    device = config_data()
    device["channel_index"] = channel
    if action != "channel":
        device["delta"] = 0
    return {
        "schema_version": 1,
        "action": action,
        "device": device,
        "ha": {
            "origin": "http://127.0.0.1:8123",
            "number_entity": "number.aquarius_plant_led_channel_" + "abcdef"[channel],
            "light_entity": "light.aquarius_plant_led_lamp",
            "resume_entity": "button.aquarius_plant_led_resume_schedule",
        },
    }


def worker_type(action):
    return {"channel": ha.HANumberWorker, "resume_program": ha.HAResumeWorker}.get(
        action, ha.HAPowerWorker
    )


def simulate(action="power_manual", *, hook=None, zero=True, channel=0):
    sim = Simulator()
    if action != "power_automatic":
        sim.state = sim.original = replace(sim.state, mode=1)
    calls = []
    config = service.Configuration.parse(config_data_ha(action, channel), simulation=True)

    class SimulatedService:
        def __init__(self, config, token, clock):
            if token != TOKEN:
                raise AssertionError("unexpected synthetic token")

        def call(self, operation, value, deadline):
            calls.append((operation, value))
            if hook:
                hook("before_" + operation, sim, deadline)
            sim.clock.advance(0.6, deadline)
            if operation == "off":
                sim.state = replace(
                    sim.state, mode=8, channels=(0,) * 6 if zero else sim.state.channels
                )
            elif operation == "on":
                sim.state = sim.original
            elif operation == "resume":
                sim.state = replace(sim.state, mode=0, channels=(11, 12, 13, 14, 15, 16))
            elif operation == "channel":
                values = list(sim.state.channels)
                values[config.device.channel] = value
                sim.state = replace(sim.state, mode=1, channels=tuple(values))
            if hook:
                hook("after_" + operation, sim, deadline)

    worker = worker_type(action)(
        config,
        TOKEN,
        service_factory=SimulatedService,
        session_factory=sim.factory,
        clock=sim.clock,
        sleeper=sim.clock.sleep,
    )
    sim.worker = worker
    result = worker.run()
    return result, sim, calls


class NativeHAWorkerSimulationTests(unittest.TestCase):
    def test_each_number_targets_only_its_one_configured_channel(self):
        for channel in range(6):
            result, sim, calls = simulate("channel", channel=channel)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(calls, [("channel", sim.original.channels[channel] - 1)])
            self.assertEqual(sim.state, sim.original)

    def test_http_completed_on_with_zero_mix_is_failure_without_raw_snapshot_replay(self):
        def missing_mix(stage, sim, deadline):
            if stage == "after_on":
                sim.state = replace(sim.state, channels=(0,) * 6)

        result, sim, calls = simulate(hook=missing_mix)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "HTTP_COMPLETED")
        self.assertEqual(sim.writes, [])
        self.assertEqual(calls, [("off", None), ("on", None)])

    def test_manual_and_automatic_power_roundtrip_use_only_native_off_then_on(self):
        for action in ("power_manual", "power_automatic"):
            for zero in (False, True):
                result, sim, calls = simulate(action, zero=zero)
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(calls, [("off", None), ("on", None)])
                self.assertEqual(sim.writes, [])
                self.assertEqual(sim.state, sim.original)
                self.assertEqual(result["ha_completion"], "HTTP_COMPLETED")
                self.assertLess(result["excursion_seconds"], 10)
                self.assertNotIn(TOKEN, json.dumps(result))

    def test_number_preserves_other_channels_and_restores_exact_manual_mix(self):
        result, sim, calls = simulate("channel")
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(calls, [("channel", 9)])
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(
            [command for _, command in sim.writes],
            [
                base.channel_frame(sim.original.channels, sim.original.controller),
                base.mode_frame(1),
            ],
        )

    def test_resume_program_then_raw_cleanup_restores_exact_original_manual_mix(self):
        result, sim, calls = simulate("resume_program")
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(calls, [("resume", None)])
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(
            [command for _, command in sim.writes],
            [
                base.channel_frame(sim.original.channels, sim.original.controller),
                base.mode_frame(1),
            ],
        )

    def test_unknown_off_uses_no_second_ha_request_and_remains_failure_after_raw_cleanup(self):
        def unknown(stage, sim, deadline):
            if stage == "after_off":
                raise service.HACompletionUnknown("synthetic lost Off completion")

        result, sim, calls = simulate(hook=unknown)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(calls, [("off", None)])
        self.assertEqual(
            [command for _, command in sim.writes],
            [
                base.mode_frame(1),
                base.channel_frame(sim.original.channels, sim.original.controller),
                base.mode_frame(1),
            ],
        )
        self.assertLess(result["excursion_seconds"], 10)

    def test_unknown_on_never_queues_raw_restore_or_another_service(self):
        def unknown(stage, sim, deadline):
            if stage == "after_on":
                raise service.HACompletionUnknown("synthetic lost On completion")

        result, sim, calls = simulate(hook=unknown)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(calls, [("off", None), ("on", None)])
        self.assertEqual(sim.writes, [])

    def test_known_undelivered_off_cannot_overwrite_a_competing_mode(self):
        def rejected(stage, sim, deadline):
            if stage == "before_off":
                sim.state = replace(sim.state, mode=8)
                raise service.HAServiceError("synthetic request rejected before dispatch")

        result, sim, calls = simulate(hook=rejected)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(sim.state.mode, 8)
        self.assertEqual(sim.writes, [])
        self.assertEqual(calls, [("off", None)])

    def test_signal_after_completed_off_still_uses_native_on_cleanup(self):
        def stop(stage, sim, deadline):
            if stage == "after_off":
                sim.worker.request_stop()

        result, sim, calls = simulate(hook=stop)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(calls, [("off", None), ("on", None)])

    def test_transient_unsafe_number_readback_cannot_authorize_later_snapshot_replay(self):
        def corrupt_once(stage, sim, deadline):
            if stage != "after_channel":
                return
            count = 0

            def read(event, simulator):
                nonlocal count
                if event == "read":
                    count += 1
                    simulator.state = replace(
                        simulator.state, controller=(99, 99) if count == 1 else (18, 60)
                    )

            sim.hook = read

        result, sim, calls = simulate("channel", hook=corrupt_once)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(sim.writes, [])
        self.assertEqual(calls, [("channel", 9)])

    def test_resume_unknown_completion_remains_fail_after_bounded_original_mix_cleanup(self):
        def unknown(stage, sim, deadline):
            if stage == "after_resume":
                raise service.HACompletionUnknown("synthetic lost Resume completion")

        result, sim, calls = simulate("resume_program", hook=unknown)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(calls, [("resume", None)])
        self.assertLess(result["excursion_seconds"], 10)


class NativeTaskHA(FakeHA):
    """Synthetic HTTP service implementing its effects through a separate TCP client.

    Its in-memory snapshot models the service contract, not HA storage durability.
    The actual HA framework and persistence have separate fixture tests.
    """

    def __init__(self, lamp, action):
        self.validation_action = action
        self.snapshot = self.off_state = None
        super().__init__(lamp, tcp_actuation=True)

    def config(self, action=None):
        data = config_data_ha(action or self.validation_action)
        data["device"]["port"] = self.lamp.port
        data["ha"]["origin"] = f"http://127.0.0.1:{self.server.server_address[1]}"
        return service.Configuration.parse(data, simulation=True)

    def actuate_tcp(self, path, payload):
        automatic = self.validation_action in ("power_automatic", "resume_program")
        config = direct.Configuration(
            self.config().device, "shutdown_automatic" if automatic else "shutdown_manual"
        )
        worker = direct.ShutdownValidationWorker(config)
        deadline = time.monotonic() + ha.legacy.HA_COORDINATOR_SECONDS
        try:
            before = worker._read(deadline, fresh=True)
            if path == "/api/services/light/turn_off":
                self.snapshot = before
                self.off_state = worker._send_mode(8, deadline, "synthetic_off")
            elif path == "/api/services/light/turn_on":
                restored = worker._send_mode(self.snapshot.mode, deadline, "synthetic_on")
                if self.snapshot.mode == 1 and restored.channels != self.snapshot.channels:
                    if self.off_state.channels != (0,) * 6 or restored.channels != (0,) * 6:
                        raise base.UnsafeState("synthetic On cannot justify snapshot restoration")
                    guard = worker._read(deadline, fresh=True)
                    if guard.mode != 1 or guard.channels != (0,) * 6:
                        raise base.UnsafeState("synthetic On zero guard changed")
                    base.ValidationWorker._command(
                        worker, self.snapshot.channels, 1, deadline, "synthetic_mix_restore"
                    )
            elif path == "/api/services/button/press":
                worker._send_mode(0, deadline, "synthetic_resume")
            elif path == "/api/services/number/set_value":
                channels = list(before.channels)
                channels[self.config().device.channel] = payload["value"]
                base.ValidationWorker._command(
                    worker, tuple(channels), 1, deadline, "synthetic_number"
                )
            else:
                raise AssertionError("unexpected native service route")
        finally:
            worker._close()


class NativeServiceTCPTests(unittest.TestCase):
    def test_native_http_manual_power_retained_and_zero_restore_exact_mix(self):
        for zero in (False, True):
            with self.subTest(zero=zero), ExclusiveLoopbackDevice() as lamp:
                lamp.state["mode"] = 1
                original = dict(lamp.state)

                def shutdown_zero(command, response):
                    if zero and command == protocol.mode_frame(8):
                        lamp.state["channels"] = (0,) * 6
                    return response

                lamp.response_filter = shutdown_zero
                with NativeTaskHA(lamp, "power_manual") as server:
                    result = ha.HAPowerWorker(server.config(), TOKEN).run()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(lamp.state, original)
            self.assertEqual(lamp.rejected_connections, 0)
            self.assertEqual(
                [row[1] for row in server.requests],
                ["/api/services/light/turn_off", "/api/services/light/turn_on"],
            )
            self.assertTrue(all(set(row[2]) == {"entity_id"} for row in server.requests))
            self.assertLess(result["excursion_seconds"], 10)

    def test_native_automatic_power_and_resume_button_preserve_original_mode_contracts(self):
        for action in ("power_automatic", "resume_program", "channel"):
            with self.subTest(action=action), ExclusiveLoopbackDevice() as lamp:
                lamp.state["mode"] = 0 if action == "power_automatic" else 1
                original = dict(lamp.state)
                with NativeTaskHA(lamp, action) as server:
                    result = worker_type(action)(server.config(), TOKEN).run()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(lamp.state, original)
            self.assertEqual(lamp.rejected_connections, 0)
            self.assertLess(result["excursion_seconds"], 10)

    def test_uncertain_native_on_allows_only_read_only_observation_after_http_failure(self):
        with ExclusiveLoopbackDevice() as lamp:
            lamp.state["mode"] = 1
            with NativeTaskHA(lamp, "power_manual") as server:

                def fail_next_service(command, response):
                    if command == protocol.mode_frame(8):
                        server.status = 500
                    return response

                lamp.response_filter = fail_next_service
                result = ha.HAPowerWorker(server.config(), TOKEN).run()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual([c for c in lamp.observed if c[2] == 0xFA], [protocol.mode_frame(8)])
        self.assertEqual(len(server.requests), 2)

    def test_cli_consumes_stdin_token_without_printing_or_persisting_it(self):
        config = service.Configuration.parse(config_data_ha(), simulation=True)
        worker = Mock()
        worker.run.return_value = {"status": "PASS", "experiment": "PASS", "recovery": "PASS"}
        output = io.StringIO()
        with (
            patch.object(ha, "_configuration", return_value=config),
            patch.object(ha.base, "PrivateReport", return_value=None),
            patch.object(ha, "HAPowerWorker", return_value=worker) as factory,
            patch("sys.stdin", SimpleNamespace(buffer=io.BytesIO((TOKEN + "\n").encode()))),
            patch.object(ha.signal, "signal"),
            contextlib.redirect_stdout(output),
        ):
            result = ha.main(
                ["--config", "/synthetic/config.json", "--report", "/synthetic/report.json"]
            )
        self.assertEqual(result, 0)
        self.assertEqual(factory.call_args.args, (config, TOKEN))
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertEqual(json.loads(output.getvalue()), worker.run.return_value)


if __name__ == "__main__":
    unittest.main()

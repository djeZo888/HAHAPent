"""Synthetic Automatic composite faults plus exclusive native TCP/HTTP simulators.

The HTTP endpoint below models HA service/state responses; it is not the Home
Assistant framework and cannot establish actual HA acceptance.
"""

import json
import socket
import socketserver
import threading
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

from tests.test_aquarius_ha_validation import TOKEN, ExclusiveLoopbackDevice
from tests.test_aquarius_task004_ha_validation import config_data_ha
from tests.test_aquarius_validation import Simulator
from tooling import aquarius_automatic_composite as composite
from tooling import aquarius_task004_ha_service as service
from tooling import aquarius_task004_validation as direct
from tooling import aquarius_validation as base

ORIGINAL = (10, 20, 30, 40, 50, 60)
PROGRAM = (11, 12, 13, 14, 15, 16)


def configuration_data():
    data = config_data_ha("power_automatic")
    data["action"] = "automatic_power_composite"
    data["expected_manual_channels"] = list(ORIGINAL)
    data["ha"]["mode_status_entity"] = "sensor.aquarius_plant_led_mode_status"
    return data


def simulate(*, hook=None, wire_hook=None, sink=None, service_seconds=0.6):
    sim = Simulator()
    sim.state = sim.original = replace(sim.state, mode=1)
    sim.hook = wire_hook
    sim.calls = []
    sim.gets = []
    sim.origin = None
    config = composite.Configuration.parse(configuration_data(), simulation=True)

    class SimulatedService:
        def __init__(self, config, token, clock):
            assert token == TOKEN

        def call(self, action, value, deadline):
            assert sim.worker.session is None, "observer must close before HA service"
            sim.calls.append(action)
            if hook:
                hook("before_" + action, sim, deadline)
            sim.clock.advance(service_seconds, deadline)
            if action == "resume":
                sim.state = replace(sim.state, mode=0, channels=PROGRAM)
            elif action == "off":
                sim.origin = sim.state.mode
                sim.state = replace(sim.state, mode=8, channels=direct.ZERO_CHANNELS)
            elif action == "on":
                sim.state = replace(sim.state, mode=0, channels=PROGRAM)
            if hook:
                hook("after_" + action, sim, deadline)

    class SimulatedReader:
        def __init__(self, config, token, clock):
            assert token == TOKEN

        def read(self, entity, deadline):
            assert sim.worker.session is None, "observer must close before HA state GET"
            sim.gets.append(entity)
            if hook:
                hook("before_get", sim, deadline)
            sim.clock.advance(0.04, deadline)
            if entity == config.mode_status_entity:
                state = {
                    "state": {0: "following_schedule", 1: "manual_override", 8: "off"}[
                        sim.state.mode
                    ]
                }
            else:
                state = {
                    "state": "off" if sim.state.mode == 8 else "on",
                    "power_control_validated": True,
                    "on_behavior": (
                        composite.AUTOMATIC_ORIGIN_BEHAVIOR
                        if sim.origin == 0
                        else "No saved manual state: On resumes the lamp's stored schedule"
                    ),
                }
            sim.ha_state = state
            if hook:
                hook("after_get", sim, deadline)
            return state

    worker = composite.AutomaticCompositeWorker(
        config,
        TOKEN,
        service_factory=SimulatedService,
        reader_factory=SimulatedReader,
        session_factory=sim.factory,
        clock=sim.clock,
        sleeper=sim.clock.sleep,
        sink=sink,
    )
    sim.worker = worker
    result = worker.run()
    return result, sim


class CompositeSimulationTests(unittest.TestCase):
    def test_native_cycle_proves_automatic_origin_and_restores_exact_manual(self):
        report, sim = simulate()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(sim.calls, ["resume", "off", "on"])
        self.assertEqual(sim.state, sim.original)
        self.assertTrue(report["automatic_origin_confirmed"])
        self.assertEqual(report["experiment_phase_seconds"], 6)
        self.assertEqual(report["recovery_reserved_seconds"], 13.5)
        self.assertEqual(report["maximum_excursion_seconds"], 20)
        self.assertLess(report["excursion_seconds"], 10)
        self.assertEqual(
            [frame for _, frame in sim.writes],
            [base.channel_frame(ORIGINAL, sim.state.controller), base.mode_frame(1)],
        )
        self.assertEqual(sim.closed, sim.connections)
        self.assertNotIn(TOKEN, json.dumps(report))

    def test_fallback_schedule_text_does_not_prove_saved_automatic_origin(self):
        def missing_origin(stage, sim, deadline):
            if stage == "after_off":
                sim.origin = None

        report, sim = simulate(hook=missing_origin)
        self.assertEqual(report["experiment"], "FAIL")
        self.assertEqual(report["recovery"], "PASS", report)
        self.assertFalse(report["automatic_origin_confirmed"])
        self.assertEqual(sim.calls, ["resume", "off"])
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(
            [frame for _, frame in sim.writes],
            [
                base.mode_frame(1),
                base.channel_frame(ORIGINAL, sim.state.controller),
                base.mode_frame(1),
            ],
        )

    def test_unknown_completion_at_each_service_has_no_later_actuation(self):
        for action, expected in (
            ("resume", ["resume"]),
            ("off", ["resume", "off"]),
            ("on", ["resume", "off", "on"]),
        ):
            with self.subTest(action=action):

                def unknown(stage, sim, deadline):
                    if stage == "after_" + action:
                        raise service.HACompletionUnknown("synthetic lost completion")

                report, sim = simulate(hook=unknown)
                self.assertEqual(report["experiment"], "FAIL")
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(report["ha_completion"], "UNKNOWN")
                self.assertEqual(sim.calls, expected)
                self.assertEqual(sim.writes, [])
                self.assertLess(report["excursion_seconds"], 20)

    def test_unknown_even_if_original_later_observed_never_claims_recovery(self):
        def unknown(stage, sim, deadline):
            if stage == "after_on":
                sim.state = sim.original
                raise service.HACompletionUnknown("synthetic delayed external restoration")

        report, sim = simulate(hook=unknown)
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual(sim.writes, [])

    def test_ignored_http200_actions_latch_state_contradiction_without_replay(self):
        for action, mode in (("resume", 1), ("off", 0), ("on", 8)):
            with self.subTest(action=action):

                def ignored(stage, sim, deadline):
                    if stage == "after_" + action:
                        sim.state = replace(sim.state, mode=mode)

                report, sim = simulate(hook=ignored)
                self.assertEqual(report["ha_completion"], "HTTP_COMPLETED")
                self.assertEqual(report["experiment"], "FAIL")
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(sim.writes, [])

    def test_known_rejection_before_on_recovers_off_zero_without_ha_retry(self):
        def rejected(stage, sim, deadline):
            if stage == "before_on":
                raise service.HAServiceError("synthetic known rejected action")

        report, sim = simulate(hook=rejected)
        self.assertEqual(report["recovery"], "PASS", report)
        self.assertEqual(report["experiment"], "FAIL")
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(sim.calls, ["resume", "off", "on"])
        self.assertEqual(len(sim.writes), 3)

    def test_wrong_manual_baseline_prevents_all_mutations(self):
        def alter(event, sim):
            if event == "read":
                sim.state = replace(sim.state, channels=(9,) + ORIGINAL[1:])

        report, sim = simulate(wire_hook=alter)
        self.assertEqual(report["experiment"], "NOT_TESTED")
        self.assertEqual(sim.calls, [])
        self.assertEqual(sim.writes, [])

    def test_inherited_final_prewrite_guard_catches_ha_get_and_intent_fsync_changes(self):
        for stage in ("ha_get", "intent_sink"):
            with self.subTest(stage=stage):
                holder = {}

                def hook(event, sim, deadline):
                    holder["sim"] = sim
                    if stage == "ha_get" and event == "after_get" and len(sim.gets) == 2:
                        sim.state = replace(sim.state, channels=(9,) + ORIGINAL[1:])

                def sink(report):
                    if (
                        stage == "intent_sink"
                        and report["events"][-1]["stage"] == "experiment_intent"
                    ):
                        sim = holder["sim"]
                        sim.state = replace(sim.state, channels=(9,) + ORIGINAL[1:])

                report, sim = simulate(hook=hook, sink=sink)
                self.assertEqual(report["experiment"], "NOT_TESTED")
                self.assertEqual(sim.calls, [])
                self.assertEqual(sim.writes, [])

    def test_one_time_competing_state_before_cleanup_prevents_restore(self):
        for field, value in (("mode", 1), ("controller", (99, 99))):
            with self.subTest(field=field):

                def compete(stage, sim, deadline):
                    if stage == "after_get" and len(sim.gets) == 6:
                        sim.state = replace(sim.state, **{field: value})

                report, sim = simulate(hook=compete)
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(sim.writes, [])

    def test_fresh_guards_after_ha_gets_block_competing_auto_or_off_state(self):
        for get_count, mutation, expected in (
            (3, {"mode": 1, "channels": (9,) * 6}, ["resume"]),
            (3, {"controller": (99, 99)}, ["resume"]),
            (4, {"mode": 1}, ["resume", "off"]),
            (4, {"channels": (1, 0, 0, 0, 0, 0)}, ["resume", "off"]),
        ):
            with self.subTest(get_count=get_count, mutation=mutation):

                def compete(stage, sim, deadline):
                    if stage == "after_get" and len(sim.gets) == get_count:
                        sim.state = replace(sim.state, **mutation)

                report, sim = simulate(hook=compete)
                self.assertEqual(report["experiment"], "FAIL", report)
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(sim.calls, expected)
                self.assertEqual(sim.writes, [])

    def test_observed_contradictory_system_then_eof_is_latched_across_normal_retry(self):
        for wrong in ("mode", "profile"):
            with self.subTest(wrong=wrong):

                def inject(stage, sim, deadline):
                    if stage != "after_resume":
                        return

                    def read_fault(event, simulator):
                        if event == "read":
                            simulator.hook = None
                            session = simulator.worker.session
                            session.last_system = (
                                1 if wrong == "mode" else 0,
                                (99, 99) if wrong == "profile" else simulator.state.controller,
                                simulator.state.version,
                                simulator.state.count,
                            )
                            raise EOFError("synthetic incomplete channels after system reply")

                    sim.hook = read_fault

                report, sim = simulate(hook=inject)
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(sim.calls, ["resume"])
                self.assertEqual(sim.writes, [])

    def test_signal_after_completed_off_recovery_ignores_repeat_signals(self):
        def stop(stage, sim, deadline):
            if stage == "after_off":
                sim.worker.request_stop()
                sim.hook = lambda event, simulator: simulator.worker.request_stop()

        report, sim = simulate(hook=stop)
        self.assertTrue(report["interrupted"])
        self.assertEqual(report["recovery"], "PASS", report)
        self.assertEqual(sim.state, sim.original)
        self.assertEqual(sim.calls, ["resume", "off"])

    def test_late_on_admission_is_rejected_and_cleanup_keeps_reserve(self):
        def slow_off(stage, sim, deadline):
            if stage == "after_off":
                sim.clock.advance(2.2, deadline)

        report, sim = simulate(hook=slow_off)
        self.assertEqual(report["experiment"], "FAIL")
        self.assertEqual(report["recovery"], "PASS", report)
        self.assertEqual(sim.calls, ["resume", "off"])
        self.assertEqual(sim.state, sim.original)
        self.assertLess(report["excursion_seconds"], 20)

    def test_full_phase_read_timeout_retains_cleanup_deadline(self):
        def timeout(stage, sim, deadline):
            if stage == "before_get" and sim.worker.phase == "off":
                sim.clock.advance(deadline - sim.clock(), deadline)
                raise composite.HAObservationError("synthetic final state read timeout")

        report, sim = simulate(hook=timeout)
        self.assertEqual(report["experiment"], "FAIL")
        self.assertEqual(report["recovery"], "PASS", report)
        self.assertEqual(sim.state, sim.original)
        self.assertLess(report["excursion_seconds"], 20)

    def test_transient_cleanup_reads_retry_without_repeating_any_write(self):
        def fault(stage, sim, deadline):
            if stage == "after_get" and len(sim.gets) == 6:
                count = [0]

                def read(event, simulator):
                    if event == "read" and count[0] < 2:
                        count[0] += 1
                        raise TimeoutError("synthetic transient guard")

                sim.hook = read

        report, sim = simulate(hook=fault)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(len(sim.writes), 2)
        self.assertEqual(sim.state, sim.original)

    def test_no_durable_report_io_inside_excursion(self):
        writes = []
        report, sim = simulate(sink=lambda report: writes.append(json.loads(json.dumps(report))))
        self.assertEqual(report["status"], "PASS", report)
        for saved in writes:
            if saved["events"][-1]["stage"] != "finished":
                self.assertNotIn("resume_ha_service_send", [e["stage"] for e in saved["events"]])
        self.assertGreater(len(writes), 1)

    def test_report_failure_before_dispatch_blocks_actions_and_after_cleanup_preserves_recovery(
        self,
    ):
        for when in ("experiment_intent", "finished"):
            with self.subTest(when=when):

                def fail(report):
                    if report["events"][-1]["stage"] == when:
                        raise OSError("synthetic evidence filesystem failure")

                report, sim = simulate(sink=fail)
                self.assertEqual(report["status"], "FAIL")
                self.assertTrue(report["reporting_error"])
                self.assertEqual(sim.state, sim.original)
                if when == "experiment_intent":
                    self.assertEqual(sim.calls, [])
                    self.assertEqual(sim.writes, [])
                else:
                    self.assertEqual(report["recovery"], "PASS")

    def test_lost_cleanup_barrier_uses_read_confirmation_without_repeating_write(self):
        def lost(event, sim):
            if event == "system" and sim.worker.cleaning:
                sim.hook = None
                raise TimeoutError("synthetic lost original Manual barrier")

        report, sim = simulate(wire_hook=lost)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(len(sim.writes), 2)
        self.assertEqual(sim.state, sim.original)

    def test_partial_cleanup_barrier_and_interrupted_quarantine_stop_new_writes(self):
        for stage in ("system", "quarantine"):
            with self.subTest(stage=stage):

                def partial(event, sim):
                    if event == stage and sim.worker.cleaning:
                        raise base.UnsafeState("synthetic incomplete reply")

                report, sim = simulate(wire_hook=partial)
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(len(sim.writes), 2 if stage == "system" else 1)

    def test_off_cleanup_requires_manual_barrier_and_extra_exact_zero_guard(self):
        def reject_on(stage, sim, deadline):
            if stage == "before_on":
                count = [0]

                def compete(event, simulator):
                    if event == "read" and simulator.worker.manual_resume_barrier_confirmed:
                        count[0] += 1
                        if count[0] == 2:
                            simulator.state = replace(simulator.state, channels=(1, 0, 0, 0, 0, 0))

                sim.hook = compete
                raise service.HAServiceError("synthetic known rejection")

        report, sim = simulate(hook=reject_on)
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(1)])

    def test_exhausted_transport_read_budget_never_spends_reserved_write_time(self):
        def loss(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.clock.advance(0.8, sim.worker.session.read_deadline)
                raise TimeoutError("synthetic repeated transport loss")

        report, sim = simulate(wire_hook=loss)
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual(sim.writes, [])
        self.assertLess(report["excursion_seconds"], 20)


class ConfigurationTests(unittest.TestCase):
    def test_only_declared_shape_mode_status_and_exact_original_are_accepted(self):
        self.assertEqual(
            composite.Configuration.parse(
                configuration_data(), simulation=True
            ).expected_manual_channels,
            ORIGINAL,
        )
        mutations = [
            lambda d: d.update(schema_version=True),
            lambda d: d.update(action="power_automatic"),
            lambda d: d.update(expected_manual_channels=[True] * 6),
            lambda d: d.update(expected_manual_channels=[0] * 7),
            lambda d: d["ha"].update(mode_status_entity="sensor.unrelated"),
            lambda d: d["ha"].update(origin="http://example.invalid"),
            lambda d: d["device"].update(delta=1),
            lambda d: d.update(extra="ignored"),
        ]
        for mutation in mutations:
            data = configuration_data()
            mutation(data)
            with self.assertRaises(ValueError):
                composite.Configuration.parse(data, simulation=True)


class CompositeHTTP:
    """Exact synthetic HTTP routes use an exclusive loopback lamp, not actual HA."""

    def __init__(self, lamp, *, unknown_on=False, corrupt_memory=False, response_override=None):
        self.lamp = lamp
        self.unknown_on = unknown_on
        self.corrupt_memory = corrupt_memory
        self.response_override = response_override
        self.origin = None
        self.requests = []
        self.actions = []
        self.unknown_closed_at = None
        self.late_effect_at = None
        endpoint = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(4)
                data = bytearray()
                try:
                    while b"\r\n\r\n" not in data:
                        data.extend(self.request.recv(4096))
                    header, body = bytes(data).split(b"\r\n\r\n", 1)
                    method, path, _ = header.split(b"\r\n")[0].decode().split()
                    headers = dict(line.split(b": ", 1) for line in header.split(b"\r\n")[1:])
                    assert headers[b"Authorization"] == ("Bearer " + TOKEN).encode()
                    endpoint.requests.append((method, path))
                    length = int(headers.get(b"Content-Length", b"0"))
                    while len(body) < length:
                        body += self.request.recv(length - len(body))
                    if endpoint.response_override:
                        self.request.sendall(endpoint.response_override)
                        return
                    if method == "POST":
                        payload = json.loads(body)
                        action = {
                            "/api/services/button/press": "resume",
                            "/api/services/light/turn_off": "off",
                            "/api/services/light/turn_on": "on",
                        }[path]
                        entity = (
                            endpoint.config().service.resume_entity
                            if action == "resume"
                            else endpoint.config().service.light_entity
                        )
                        assert payload == {"entity_id": entity}
                        endpoint.actions.append(action)
                        if action == "on" and endpoint.unknown_on:
                            # HTTP completion is lost before a delayed device effect;
                            # the worker must remain read-only even when it sees Auto.
                            self.request.shutdown(socket.SHUT_WR)
                            endpoint.unknown_closed_at = time.monotonic()
                            time.sleep(0.1)
                            endpoint.actuate(action)
                            endpoint.late_effect_at = time.monotonic()
                            return
                        endpoint.actuate(action)
                        response = b"[]"
                    else:
                        entity = path.removeprefix("/api/states/")
                        config = endpoint.config()
                        with endpoint.lamp.lock:
                            mode = endpoint.lamp.state["mode"]
                        if entity == config.mode_status_entity:
                            state, attributes = (
                                {0: "following_schedule", 1: "manual_override", 8: "off"}[mode],
                                {},
                            )
                        else:
                            assert entity == config.service.light_entity
                            state = "off" if mode == 8 else "on"
                            attributes = {
                                "power_control_validated": True,
                                "on_behavior": composite.AUTOMATIC_ORIGIN_BEHAVIOR
                                if endpoint.origin == 0 and not endpoint.corrupt_memory
                                else "No saved manual state: On resumes the lamp's stored schedule",
                            }
                        response = json.dumps(
                            {"entity_id": entity, "state": state, "attributes": attributes}
                        ).encode()
                    self.request.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: "
                        + str(len(response)).encode()
                        + b"\r\nConnection: close\r\n\r\n"
                        + response
                    )
                except (ConnectionError, OSError, base.ValidationError):
                    return

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def config(self):
        data = configuration_data()
        data["device"]["port"] = self.lamp.port
        data["ha"]["origin"] = f"http://127.0.0.1:{self.server.server_address[1]}"
        return composite.Configuration.parse(data, simulation=True)

    def actuate(self, action):
        config = self.config().device
        deadline = time.monotonic() + 3
        session = direct.ShutdownWireSession(config, deadline, time.monotonic)
        try:
            before = session.read_state(deadline)
            if action == "off":
                self.origin = before.mode
                mode = 8
            else:
                mode = 0
            command = (
                base.mode_frame(mode) if mode != 8 else base.frame(bytes((0xE1, 0xFA, 0xDB, 8)))
            )
            session.send(command, deadline)
            session.quarantine(base.WRITE_DRAIN_PAUSE, deadline, (command,))
            assert session.system(deadline)[0] == mode
        finally:
            session.close()
        session = direct.ShutdownWireSession(config, deadline, time.monotonic)
        try:
            assert session.read_state(deadline).mode == mode
        finally:
            session.close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


def prepare_lamp(lamp):
    lamp.state.update(mode=1, channels=ORIGINAL)

    def shutdown_zero(command, response):
        if command[1:4] == b"\xe1\xfa\xdb" and command[4] == 8:
            lamp.state["channels"] = direct.ZERO_CHANNELS
        return response

    lamp.response_filter = shutdown_zero


class NativeLoopbackCompositeTests(unittest.TestCase):
    def test_exclusive_tcp_handoff_real_http_state_origin_and_exact_manual_cleanup(self):
        with ExclusiveLoopbackDevice() as lamp:
            prepare_lamp(lamp)
            with CompositeHTTP(lamp) as endpoint:
                report = composite.AutomaticCompositeWorker(endpoint.config(), TOKEN).run()
                self.assertEqual(report["status"], "PASS", report)
                self.assertTrue(report["automatic_origin_confirmed"])
                self.assertEqual(endpoint.actions, ["resume", "off", "on"])
                self.assertEqual(lamp.state, {"mode": 1, "channels": ORIGINAL})
                self.assertEqual(lamp.rejected_connections, 0)
                self.assertLess(report["excursion_seconds"], 10)
                mutations = [
                    x for x in lamp.observed if x not in (base.SYSTEM_QUERY, base.CHANNEL_QUERY)
                ]
                self.assertEqual(
                    mutations,
                    [
                        base.mode_frame(0),
                        base.frame(bytes((0xE1, 0xFA, 0xDB, 8))),
                        base.mode_frame(0),
                        base.channel_frame(ORIGINAL, (18, 60)),
                        base.mode_frame(1),
                    ],
                )

    def test_unknown_on_late_effect_never_causes_manual_snapshot_replay(self):
        with ExclusiveLoopbackDevice() as lamp:
            prepare_lamp(lamp)
            with CompositeHTTP(lamp, unknown_on=True) as endpoint:
                report = composite.AutomaticCompositeWorker(endpoint.config(), TOKEN).run()
                self.assertEqual(report["experiment"], "FAIL", report)
                self.assertEqual(report["recovery"], "FAIL")
                self.assertEqual(report["ha_completion"], "UNKNOWN")
                self.assertEqual(lamp.state["mode"], 0)
                self.assertFalse(any(x[1:3] == b"\xe2\xfa" for x in lamp.observed))
                self.assertEqual(endpoint.actions, ["resume", "off", "on"])
                self.assertEqual(lamp.rejected_connections, 0)
                self.assertGreater(endpoint.late_effect_at, endpoint.unknown_closed_at)

    def test_real_http_fallback_origin_blocks_on_and_uses_guarded_off_zero_cleanup(self):
        with ExclusiveLoopbackDevice() as lamp:
            prepare_lamp(lamp)
            with CompositeHTTP(lamp, corrupt_memory=True) as endpoint:
                report = composite.AutomaticCompositeWorker(endpoint.config(), TOKEN).run()
                self.assertEqual(report["experiment"], "FAIL", report)
                self.assertEqual(report["recovery"], "PASS", report)
                self.assertFalse(report["automatic_origin_confirmed"])
                self.assertEqual(endpoint.actions, ["resume", "off"])
                self.assertEqual(lamp.state, {"mode": 1, "channels": ORIGINAL})
                self.assertEqual(lamp.rejected_connections, 0)

    def test_reader_rejects_wrong_route_without_opening_socket(self):
        config = composite.Configuration.parse(configuration_data(), simulation=True)
        with patch.object(composite.socket, "create_connection") as connect:
            with self.assertRaises(composite.HAObservationError):
                composite.HAStateReader(config, TOKEN).read(
                    "sensor.unrelated", time.monotonic() + 1
                )
            connect.assert_not_called()

    def test_reader_rejects_unframed_ambiguous_redirect_and_private_body(self):
        sensitive = b"synthetic-body-not-for-reports"
        responses = [
            b"HTTP/1.1 302 Found\r\nLocation: https://example.invalid/\r\n\r\n" + sensitive,
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Length: 65537\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\n{}",
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}",
        ]
        for attributes in (
            '{"on_behavior":"No saved manual state",'
            '"on_behavior":"On resumes the lamp\'s stored schedule"}',
            '{"power_control_validated":false,"power_control_validated":true}',
            '{"unrelated":NaN}',
        ):
            body = (
                '{"entity_id":"light.aquarius_plant_led_lamp","state":"off",'
                '"attributes":' + attributes + "}"
            ).encode()
            responses.append(
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
        with ExclusiveLoopbackDevice() as lamp:
            for response in responses:
                with self.subTest(response=response[:20]):
                    with CompositeHTTP(lamp, response_override=response) as endpoint:
                        reader = composite.HAStateReader(endpoint.config(), TOKEN)
                        with self.assertRaises(composite.HAObservationError) as raised:
                            reader.read(
                                endpoint.config().service.light_entity, time.monotonic() + 1
                            )
                        self.assertNotIn(sensitive.decode(), str(raised.exception))
                        self.assertNotIn(TOKEN, str(raised.exception))
                        self.assertEqual(len(endpoint.requests), 1)


if __name__ == "__main__":
    unittest.main()

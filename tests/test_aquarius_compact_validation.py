"""Compact worker failure simulation and real loopback HTTP/exclusive TCP tests.

The HTTP server models HA and uses fictional lamp state; it is not HA framework
or actual-device acceptance. Expected vectors below do not import the mixer.
"""

import contextlib
import copy
import io
import json
import socket
import socketserver
import tempfile
import threading
import time
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import Mock, patch

from tests.aquarius_tcp_helpers import protocol, system_reply
from tests.test_aquarius_ha_validation import TOKEN, ExclusiveLoopbackDevice
from tests.test_aquarius_validation import Simulator, config_data
from tooling import aquarius_compact_validation as compact
from tooling import aquarius_task004_validation as direct
from tooling import aquarius_validation as base

BASELINE = (1, 1, 0, 0, 0, 0)
RED_ONE = (1, 0, 0, 0, 0, 0)
RED_TWO = (2, 0, 0, 0, 0, 0)
RED_FIVE = (5, 0, 0, 0, 0, 0)
ZERO = (0,) * 6


def colour(level=1):
    action = {"kind": "colour", "rgb_color": [255, 0, 0], "expected_channels": list(RED_FIVE)}
    if level is not None:
        action.update(intensity=level, expected_channels=[level, 0, 0, 0, 0, 0])
    return action


def intensity(value):
    return {"kind": "intensity", "value": value, "expected_channels": [value, 0, 0, 0, 0, 0]}


PLANS = ([colour()], [colour(), intensity(2), intensity(0)], [intensity(0), colour(None)])


def configuration_data(plan=0):
    device = config_data()
    del device["channel_index"], device["delta"]
    return {
        "schema_version": 1,
        "device": device,
        "ha": {
            "origin": "http://127.0.0.1:8123",
            "light_entity": "light.aquarius_plant_led_lamp",
            "intensity_entity": "number.aquarius_plant_led_intensity",
            "mode_status_entity": "sensor.aquarius_plant_led_mode_status",
        },
        "actions": copy.deepcopy(PLANS[plan]),
    }


def simulate(plan=0, *, hook=None, wire_hook=None, sink=None, service_seconds=0.4):
    sim = Simulator()
    sim.state = sim.original = replace(sim.state, channels=BASELINE)
    sim.hook, sim.calls, sim.gets = wire_hook, [], []
    config = compact.Configuration.parse(configuration_data(plan), simulation=True)

    class Service:
        def __init__(self, config, token, clock):
            assert token == TOKEN

        def call(self, index, deadline):
            assert sim.worker.session is None, "observer must close before HTTP"
            sim.calls.append(index)
            if hook:
                hook("before_service", sim, deadline)
            sim.clock.advance(service_seconds, deadline)
            action = config.actions[index]
            sim.state = replace(sim.state, mode=action.mode, channels=action.expected_channels)
            if hook:
                hook("after_service", sim, deadline)

    class Reader:
        def __init__(self, config, token, clock):
            assert token == TOKEN

        def read(self, entity, deadline):
            assert sim.worker.session is None, "observer must close before GET"
            sim.gets.append(entity)
            sim.clock.advance(0.02, deadline)
            result = {
                "state": {0: "following_schedule", 1: "manual_override", 8: "off"}[sim.state.mode]
            }
            if hook:
                hook("after_get", sim, deadline)
            return result

    sim.worker = compact.CompactWorker(
        config,
        TOKEN,
        service_factory=Service,
        reader_factory=Reader,
        session_factory=sim.factory,
        clock=sim.clock,
        sleeper=sim.clock.sleep,
        sink=sink,
    )
    return sim.worker.run(), sim


class ConfigurationTests(unittest.TestCase):
    def test_three_plans_are_immutable_and_fix_their_absolute_budgets(self):
        for index in range(3):
            raw = configuration_data(index)
            config = compact.Configuration.parse(raw, simulation=True)
            self.assertEqual(config.maximum_seconds, 10 if index == 0 else 20)
            self.assertEqual(config.experiment_seconds, 3 if index == 0 else 6)
            self.assertEqual(config.cleanup_seconds, 9.5 if index == 0 else 19.5)
            raw["actions"][0]["expected_channels"][0] = 100
            self.assertLessEqual(max(config.actions[0].expected_channels), 5)
            with self.assertRaises(FrozenInstanceError):
                config.actions[0].kind = "other"

    def test_invalid_shape_version_plan_length_and_bounds_are_rejected(self):
        for change in (
            {"schema_version": True},
            {"actions": []},
            {"actions": PLANS[0] * 4},
            {"maximum": 30},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                compact.Configuration.parse({**configuration_data(), **change}, simulation=True)
        for value in (-1, 6, True, 1.0, None, "1"):
            data = configuration_data()
            data["actions"][0]["intensity"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                compact.Configuration.parse(data, simulation=True)

    def test_rgb_vectors_expectations_and_arbitrary_service_fields_are_strict(self):
        for change in (
            {"rgb_color": [True, 0, 0]},
            {"rgb_color": [256, 0, 0]},
            {"rgb_color": [0, 0]},
            {"expected_channels": [6, 0, 0, 0, 0, 0]},
            {"expected_channels": [True] * 6},
            {"expected_channels": [0] * 6},
            {"transition": 1},
            {"entity_id": "light.other"},
        ):
            data = configuration_data()
            data["actions"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compact.Configuration.parse(data, simulation=True)

    def test_private_origin_and_exact_entities_are_enforced(self):
        for origin in (
            "http://8.8.8.8",
            "http://example.invalid",
            "http://127.0.0.1/api",
            "http://" + "a:b@127.0.0.1",
            "ftp://127.0.0.1",
            "http://[::1]",
        ):
            data = configuration_data()
            data["ha"]["origin"] = origin
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                compact.Configuration.parse(data, simulation=True)
        for field in ("light_entity", "intensity_entity", "mode_status_entity"):
            for value in (
                "all",
                ["light.aquarius_plant_led_lamp"],
                "light.unrelated",
                "light.aquarius_plant_led_lamp/extra",
            ):
                data = configuration_data()
                data["ha"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    compact.Configuration.parse(data, simulation=True)
        with self.assertRaises(ValueError):
            compact.Configuration.parse(configuration_data())

    def test_configuration_file_mode_symlink_and_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(configuration_data()))
            path.chmod(0o600)
            self.assertEqual(len(compact._configuration(path, simulation=True).actions), 1)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                compact._configuration(path, simulation=True)
            path.chmod(0o600)
            link = Path(temporary) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                compact._configuration(link, simulation=True)
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(ValueError):
                compact._configuration(path, simulation=True)

    def test_check_config_never_reads_token_constructs_worker_or_opens_network(self):
        config = compact.Configuration.parse(configuration_data(), simulation=True)
        with (
            patch.object(compact, "_configuration", return_value=config),
            patch.object(compact, "CompactWorker") as worker,
            patch.object(compact.sys, "stdin") as stdin,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(compact.main(["--config", "synthetic.json", "--check-config"]), 0)
            worker.assert_not_called()
            stdin.read.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "CONFIG_VALID", "actions": 1})


class SimulationTests(unittest.TestCase):
    def test_all_plans_require_known_completion_then_only_one_automatic_cleanup(self):
        for plan in range(3):
            report, sim = simulate(plan)
            self.assertEqual(report["status"], "PASS", report)
            self.assertEqual(sim.calls, list(range(len(PLANS[plan]))))
            self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])
            self.assertEqual(sim.state.mode, 0)
            self.assertEqual(sim.closed, sim.connections)
            self.assertLess(report["excursion_seconds"], report["maximum_excursion_seconds"])
            self.assertNotIn(TOKEN, json.dumps(report))

    def test_initial_manual_off_high_or_unstable_output_never_actuates(self):
        for field, value in (
            ("mode", 1),
            ("mode", 8),
            ("channels", (6,) * 6),
            ("controller", (99, 99)),
        ):

            def invalid(event, sim):
                if event == "read":
                    sim.state = replace(sim.state, **{field: value})

            report, sim = simulate(wire_hook=invalid)
            self.assertEqual(report["experiment"], "NOT_TESTED", report)
            self.assertEqual(sim.calls + sim.writes, [])

    def test_post_intent_guard_prevents_stale_snapshot_after_slow_persistence(self):
        holder = {}

        def observe(event, sim):
            holder["sim"] = sim

        def sink(report):
            if report["events"][-1]["stage"] == "experiment_intent":
                sim = holder["sim"]
                sim.state = replace(sim.state, channels=(2, 1, 0, 0, 0, 0))

        report, sim = simulate(wire_hook=observe, sink=sink)
        self.assertEqual(report["experiment"], "NOT_TESTED")
        self.assertEqual(sim.calls + sim.writes, [])

    def test_unknown_at_every_action_never_allows_later_ha_or_raw_writes(self):
        for index in range(3):

            def unknown(event, sim, deadline):
                if event == "after_service" and sim.calls[-1] == index:
                    raise compact.HACompletionUnknown("synthetic completion lost")

            report, sim = simulate(1, hook=unknown)
            self.assertEqual(report["ha_completion"], "UNKNOWN")
            self.assertEqual(report["recovery"], "FAIL")
            self.assertEqual(sim.calls, list(range(index + 1)))
            self.assertEqual(sim.writes, [])

    def test_unexpected_adapter_failure_is_also_unknown_not_permission_for_cleanup(self):
        def unknown(event, sim, deadline):
            if event == "after_service":
                raise RuntimeError("synthetic unclassified service failure")

        report, sim = simulate(1, hook=unknown)
        self.assertEqual(report["ha_completion"], "UNKNOWN")
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual(sim.calls, [0])
        self.assertEqual(sim.writes, [])

    def test_completed_request_with_wrong_output_latches_no_cleanup(self):
        for mutation in ({"mode": 0}, {"channels": RED_TWO}, {"controller": (99, 99)}):

            def wrong(event, sim, deadline):
                if event == "after_service":
                    sim.state = replace(sim.state, **mutation)

            report, sim = simulate(hook=wrong)
            self.assertEqual(report["ha_completion"], "HTTP_COMPLETED")
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(sim.writes, [])

    def test_one_time_unsafe_reply_cannot_be_forgotten_by_later_good_read(self):
        for fault in (base.UnsafeState("partial response"), base.UnsafeState("query echo")):
            failed = False

            def wire(event, sim):
                nonlocal failed
                if event == "read" and sim.calls and not failed:
                    failed = True
                    raise fault

            report, sim = simulate(wire_hook=wire)
            self.assertEqual(report["recovery"], "FAIL")
            self.assertEqual(sim.writes, [])

    def test_phase_change_during_ha_get_blocks_next_action_and_cleanup(self):
        def competing(event, sim, deadline):
            if event == "after_get" and sim.calls:
                sim.state = replace(sim.state, channels=RED_FIVE)

        report, sim = simulate(1, hook=competing)
        self.assertEqual(sim.calls, [0])
        self.assertEqual(sim.writes, [])
        self.assertEqual(report["status"], "FAIL")

    def test_known_rejection_preserves_only_previous_owned_phase(self):
        def rejected(event, sim, deadline):
            if event == "before_service" and sim.calls[-1] == 1:
                raise compact.HAServiceError("synthetic known rejection")

        report, sim = simulate(1, hook=rejected)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["recovery"], "PASS")
        self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])

    def test_signal_after_completed_service_cleans_up_but_remains_failure(self):
        def stop(event, sim, deadline):
            if event == "after_service":
                sim.worker.request_stop()

        report, sim = simulate(1, hook=stop)
        self.assertEqual(sim.calls, [0])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["recovery"], "PASS")
        self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])

    def test_transient_cleanup_guard_read_retries_only_reads(self):
        failed = False

        def fault(event, sim):
            nonlocal failed
            if event == "read" and sim.worker.cleaning and not failed:
                failed = True
                raise socket.timeout("synthetic guard timeout")

        report, sim = simulate(wire_hook=fault)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])

    def test_persistent_cleanup_loss_and_budget_exhaustion_never_actuate(self):
        for exhausted in (False, True):

            def fault(event, sim):
                if event == "read" and sim.worker.cleaning:
                    if exhausted:
                        sim.clock.sleep(4)
                    raise socket.timeout("synthetic unavailable")

            report, sim = simulate(wire_hook=fault)
            self.assertEqual(report["recovery"], "FAIL")
            self.assertEqual(sim.writes, [])

    def test_cleanup_barrier_loss_confirms_fresh_automatic_without_resending(self):
        def lost(event, sim):
            if event == "system" and sim.worker.cleaning:
                raise EOFError("synthetic lost barrier")

        report, sim = simulate(wire_hook=lost)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])

    def test_automatic_drift_after_cleanup_is_not_a_snapshot_mismatch(self):
        def drift(event, sim):
            if event == "mode_sent":
                sim.state = replace(sim.state, channels=(3, 2, 1, 0, 0, 0))

        report, sim = simulate(wire_hook=drift)
        self.assertEqual(report["status"], "PASS", report)
        self.assertNotEqual(sim.state.channels, BASELINE)

    def test_already_automatic_is_preserved_without_writing(self):
        def automatic(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.state = replace(sim.state, mode=0, channels=(3, 1, 0, 0, 0, 0))

        report, sim = simulate(wire_hook=automatic)
        self.assertEqual(report["recovery"], "PASS")
        self.assertEqual(sim.writes, [])

    def test_phase_exhaustion_skips_following_action_and_keeps_cleanup_reserve(self):
        report, sim = simulate(1, service_seconds=1.6)
        self.assertEqual(report["status"], "FAIL")
        self.assertLess(len(sim.calls), 3)
        self.assertEqual(report["recovery"], "PASS")
        self.assertLess(report["excursion_seconds"], 20)

    def test_reporting_failure_before_start_has_no_actions(self):
        def failed(report):
            raise OSError("synthetic evidence unavailable")

        report, sim = simulate(sink=failed)
        self.assertEqual(report["experiment"], "NOT_TESTED")
        self.assertEqual(sim.calls + sim.writes, [])

    def test_mode_or_profile_before_lost_channel_reply_permanently_blocks_cleanup(self):
        for observed in ((0, (18, 60), (2, 5), 6), (1, (99, 99), (2, 5), 6)):
            failed = False

            def fault(event, sim):
                nonlocal failed
                if event == "read" and sim.calls and not failed:
                    failed = True
                    sim.worker.session.last_system = observed
                    raise EOFError("synthetic channel reply lost after contradictory system")

            report, sim = simulate(wire_hook=fault)
            self.assertEqual(report["recovery"], "FAIL")
            self.assertEqual(sim.writes, [])

    def test_changed_cleanup_vector_is_not_overwritten(self):
        def competing(event, sim):
            if event == "read" and sim.worker.cleaning:
                sim.state = replace(sim.state, channels=RED_FIVE)

        report, sim = simulate(wire_hook=competing)
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual(sim.writes, [])

    def test_ignored_cleanup_and_ambiguous_barrier_never_resend_automatic(self):
        for ambiguous in (False, True):

            def fault(event, sim):
                if not ambiguous and event == "mode_sent":
                    sim.state = replace(sim.state, mode=1)
                if ambiguous and event == "system" and sim.worker.cleaning:
                    raise base.UnsafeState("synthetic partial cleanup barrier")

            report, sim = simulate(wire_hook=fault)
            self.assertEqual(report["recovery"], "FAIL")
            self.assertEqual([frame for _, frame in sim.writes], [base.mode_frame(0)])

    def test_expended_cleanup_reserve_never_sends_a_late_command(self):
        def spend(event, sim, deadline):
            if event == "after_get" and sim.calls:
                sim.clock.value = sim.worker.excursion_started + 8

        report, sim = simulate(hook=spend)
        self.assertEqual(report["recovery"], "FAIL")
        self.assertEqual(sim.writes, [])

    def test_preflight_signal_and_final_reporting_failure_have_distinct_outcomes(self):
        def stop(event, sim):
            if event == "read":
                sim.worker.request_stop()

        report, sim = simulate(wire_hook=stop)
        self.assertEqual(report["experiment"], "NOT_TESTED")
        self.assertEqual(sim.calls + sim.writes, [])

        def sink(report):
            if report["events"][-1]["stage"] == "finished":
                raise OSError("synthetic final evidence failure")

        report, sim = simulate(sink=sink)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["recovery"], "PASS")
        self.assertEqual(sim.state.mode, 0)


class HTTPTransportTests(unittest.TestCase):
    def test_expired_deadline_or_unplanned_index_never_dispatches(self):
        config = compact.Configuration.parse(configuration_data(), simulation=True)
        service = compact.Service(config, TOKEN)
        with patch.object(compact.socket, "create_connection") as create:
            for index in (-1, 1, True, 0.0, "0"):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    service.call(index, time.monotonic() + 1)
            with self.assertRaises(compact.HAServiceError):
                service.call(0, time.monotonic() - 1)
            create.assert_not_called()

    def test_fixed_route_payloads_include_literal_zero_and_omit_unspecified_brightness(self):
        for plan in range(3):
            config = compact.Configuration.parse(configuration_data(plan), simulation=True)
            service = compact.Service(config, TOKEN)
            for index, action in enumerate(config.actions):
                connection = Mock()
                connection.recv.return_value = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
                with patch.object(compact.socket, "create_connection", return_value=connection):
                    service.call(index, time.monotonic() + 1)
                header, body = connection.sendall.call_args.args[0].split(b"\r\n\r\n", 1)
                payload = json.loads(body)
                if action.kind == "colour":
                    self.assertTrue(header.startswith(b"POST /api/services/light/turn_on "))
                    self.assertEqual(payload["entity_id"], config.light_entity)
                    self.assertEqual(payload["rgb_color"], list(action.rgb_color))
                    self.assertEqual("brightness_pct" in payload, action.intensity is not None)
                else:
                    self.assertTrue(header.startswith(b"POST /api/services/number/set_value "))
                    self.assertEqual(
                        payload, {"entity_id": config.intensity_entity, "value": action.intensity}
                    )

    def test_unknown_http_results_never_retry_or_disclose_error_bodies(self):
        config = compact.Configuration.parse(configuration_data(), simulation=True)
        for response in (
            b"",
            b"HTTP/1.1 500 Failed\r\n\r\n",
            b"HTTP/1.1 302 Redirect\r\n\r\n",
            b"invalid\r\n\r\n",
            b"x" * 17000,
        ):
            connection = Mock()
            connection.recv.return_value = response
            with patch.object(
                compact.socket, "create_connection", return_value=connection
            ) as create:
                with self.assertRaises(compact.HACompletionUnknown) as error:
                    compact.Service(config, TOKEN).call(0, time.monotonic() + 1)
                self.assertNotIn(TOKEN, str(error.exception))
                create.assert_called_once()

    def test_partial_send_and_receive_timeout_are_unknown_but_connect_failure_is_not(self):
        config = compact.Configuration.parse(configuration_data(), simulation=True)
        for method in ("sendall", "recv"):
            connection = Mock()
            getattr(connection, method).side_effect = socket.timeout(TOKEN)
            with patch.object(compact.socket, "create_connection", return_value=connection):
                with self.assertRaises(compact.HACompletionUnknown) as error:
                    compact.Service(config, TOKEN).call(0, time.monotonic() + 1)
                self.assertNotIn(TOKEN, str(error.exception))
        with patch.object(compact.socket, "create_connection", side_effect=OSError(TOKEN)):
            with self.assertRaises(compact.HAServiceError) as error:
                compact.Service(config, TOKEN).call(0, time.monotonic() + 1)
            self.assertNotIsInstance(error.exception, compact.HACompletionUnknown)


class NativeHTTP:
    """Fixed synthetic recipes implemented through the exclusive TCP simulator."""

    def __init__(self, lamp, plan=0, *, late=False):
        self.lamp, self.plan, self.late = lamp, plan, late
        self.requests, self.errors, self.gets = [], [], []
        self.finished = threading.Event()
        server = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    data = bytearray()
                    while b"\r\n\r\n" not in data:
                        chunk = self.request.recv(1024)
                        if not chunk:
                            return
                        data.extend(chunk)
                    header, body = bytes(data).split(b"\r\n\r\n", 1)
                    lines = header.decode().split("\r\n")
                    method, path, _ = lines[0].split(" ")
                    headers = dict(line.split(": ", 1) for line in lines[1:])
                    assert headers["Authorization"] == f"Bearer {TOKEN}"
                    if method == "GET":
                        server.gets.append(path)
                        entity = server.config().mode_status_entity
                        assert path == "/api/states/" + entity
                        state = {0: "following_schedule", 1: "manual_override", 8: "off"}[
                            lamp.state["mode"]
                        ]
                        result = {"entity_id": entity, "state": state, "attributes": {}}
                    else:
                        length = int(headers["Content-Length"])
                        while len(body) < length:
                            body += self.request.recv(1024)
                        payload = json.loads(body[:length])
                        index = len(server.requests)
                        server.requests.append((path, payload))
                        if server.late:
                            self.request.shutdown(socket.SHUT_RDWR)
                            self.request.close()
                            time.sleep(0.05)
                        server.actuate(index, path, payload)
                        server.finished.set()
                        if server.late:
                            return
                        result = []
                    response = json.dumps(result).encode()
                    self.request.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: "
                        + str(len(response)).encode()
                        + b"\r\nConnection: close\r\n\r\n"
                        + response
                    )
                except Exception as error:
                    server.errors.append(type(error).__name__)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def config(self):
        data = configuration_data(self.plan)
        data["device"]["port"] = self.lamp.port
        data["ha"]["origin"] = f"http://127.0.0.1:{self.server.server_address[1]}"
        return compact.Configuration.parse(data, simulation=True)

    def actuate(self, index, path, payload):
        config = self.config()
        action = config.actions[index]
        expected_payload = (
            {"entity_id": config.intensity_entity, "value": action.intensity}
            if action.kind == "intensity"
            else {"entity_id": config.light_entity, "rgb_color": list(action.rgb_color)}
        )
        if action.kind == "colour" and action.intensity is not None:
            expected_payload["brightness_pct"] = action.intensity
        assert payload == expected_payload
        assert path == (
            "/api/services/light/turn_on"
            if action.kind == "colour"
            else "/api/services/number/set_value"
        )
        worker = direct.ShutdownValidationWorker(
            direct.Configuration(config.device, "shutdown_automatic")
        )
        deadline = time.monotonic() + 3
        try:
            before = worker._read(deadline, fresh=True)
            if action.mode == 8:
                worker._send_mode(8, deadline, "synthetic_off")
            else:
                if before.mode == 8:
                    wake = base.ValidationWorker._command(
                        worker, None, 1, deadline, "synthetic_wake"
                    )
                    assert wake.channels == ZERO
                    assert worker._read(deadline, fresh=True) == wake
                base.ValidationWorker._command(
                    worker, action.expected_channels, 1, deadline, "synthetic_bulk"
                )
        finally:
            worker._close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


def prepare_lamp(lamp):
    lamp.state.update(mode=0, channels=BASELINE)

    def off_zero(command, response):
        if command == protocol.mode_frame(8):
            lamp.state["channels"] = ZERO
        return response

    lamp.response_filter = off_zero


class NativeLoopbackTests(unittest.TestCase):
    def test_transient_cleanup_read_and_lost_barrier_use_fresh_reads_without_replay(self):
        for barrier in (False, True):
            with self.subTest(barrier=barrier), ExclusiveLoopbackDevice() as lamp:
                prepare_lamp(lamp)
                with NativeHTTP(lamp) as http:
                    worker = compact.CompactWorker(http.config(), TOKEN)
                    original = lamp.response_filter
                    failed = False

                    def lose_once(command, response):
                        nonlocal failed
                        response = original(command, response)
                        if (
                            command == base.SYSTEM_QUERY
                            and worker.cleaning
                            and worker.cleanup_sent == barrier
                            and not failed
                        ):
                            failed = True
                            return None if barrier else b""
                        return response

                    lamp.response_filter = lose_once
                    result = worker.run()
                self.assertTrue(failed)
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(lamp.observed.count(base.mode_frame(0)), 1)
                self.assertLess(result["excursion_seconds"], 10)

    def test_one_time_partial_or_query_echo_never_grants_cleanup_permission(self):
        for partial in (False, True):
            with self.subTest(partial=partial), ExclusiveLoopbackDevice() as lamp:
                prepare_lamp(lamp)
                with NativeHTTP(lamp) as http:
                    original = lamp.response_filter
                    failed = False

                    def unsafe_once(command, response):
                        nonlocal failed
                        response = original(command, response)
                        if command == base.SYSTEM_QUERY and http.finished.is_set() and not failed:
                            failed = True
                            return response[:8] if partial else base.SYSTEM_QUERY
                        return response

                    lamp.response_filter = unsafe_once
                    result = compact.CompactWorker(http.config(), TOKEN).run()
                self.assertTrue(failed)
                self.assertEqual(result["recovery"], "FAIL")
                self.assertNotIn(base.mode_frame(0), lamp.observed)

    def test_all_three_plans_use_real_http_exclusive_tcp_and_automatic_only_cleanup(self):
        for plan in range(3):
            with self.subTest(plan=plan), ExclusiveLoopbackDevice() as lamp:
                prepare_lamp(lamp)
                with NativeHTTP(lamp, plan) as http:
                    result = compact.CompactWorker(http.config(), TOKEN).run()
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(http.errors, [])
                self.assertEqual(lamp.rejected_connections, 0)
                self.assertEqual(lamp.state["mode"], 0)
                self.assertEqual(lamp.observed.count(base.mode_frame(0)), 1)
                self.assertEqual(len(http.requests), len(PLANS[plan]))
                self.assertLess(result["excursion_seconds"], result["maximum_excursion_seconds"])

    def test_lost_http_before_late_effect_never_enqueues_recovery_or_second_action(self):
        with ExclusiveLoopbackDevice() as lamp:
            prepare_lamp(lamp)
            with NativeHTTP(lamp, 1, late=True) as http:
                result = compact.CompactWorker(http.config(), TOKEN).run()
                self.assertTrue(http.finished.wait(1))
            self.assertEqual(result["ha_completion"], "UNKNOWN")
            self.assertEqual(result["recovery"], "FAIL")
            self.assertEqual(len(http.requests), 1)
            self.assertEqual(lamp.state, {"mode": 1, "channels": RED_ONE})
            self.assertNotIn(base.mode_frame(0), lamp.observed)

    def test_one_time_wrong_profile_response_cannot_be_repaired_into_cleanup_permission(self):
        with ExclusiveLoopbackDevice() as lamp:
            prepare_lamp(lamp)
            failed = False
            with NativeHTTP(lamp) as http:
                original = lamp.response_filter

                def profile_fault(command, response):
                    nonlocal failed
                    response = original(command, response)
                    if command == base.SYSTEM_QUERY and http.finished.is_set() and not failed:
                        failed = True
                        return system_reply(lamp.state["mode"], controller=(99, 99))
                    return response

                lamp.response_filter = profile_fault
                result = compact.CompactWorker(http.config(), TOKEN).run()
            self.assertEqual(result["status"], "FAIL")
            self.assertNotIn(base.mode_frame(0), lamp.observed)


if __name__ == "__main__":
    unittest.main()

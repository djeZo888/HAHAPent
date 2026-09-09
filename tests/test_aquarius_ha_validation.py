"""Synthetic HA service and independent lamp-TCP validation; no protected targets."""

import contextlib
import io
import json
import socket
import socketserver
import threading
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.test_aquarius_validation import LoopbackDevice, Simulator, config_data
from tooling import aquarius_ha_validation as ha
from tooling import aquarius_validation as base

TOKEN = "synthetic-memory-only-token"


def ha_data(action="channel"):
    device = config_data()
    if action == "manual":
        device["delta"] = 0
    return {
        "schema_version": 1,
        "device": device,
        "ha": {
            "origin": "http://127.0.0.1:8123",
            "number_entity": "number.aquarius_plant_led_channel_a",
            "mode_entity": "select.aquarius_plant_led_operating_mode",
        },
        "action": action,
        "restore_mode_via_ha": action == "manual",
    }


class HAAdapterSimulationTests(unittest.TestCase):
    def run_worker(self, action="channel", hook=None, *, sink=None):
        simulator = Simulator()
        calls = []
        config = ha.Configuration.parse(ha_data(action), simulation=True)

        class Service:
            def __init__(self, config, token, clock):
                self.clock = clock
                self.config = config
                if token != TOKEN:
                    raise AssertionError("unexpected synthetic credential")

            def call(self, operation, value, deadline):
                simulator.clock.advance(0.6, deadline)
                calls.append((operation, value))
                if operation == "channel":
                    values = list(simulator.state.channels)
                    values[self.config.device.channel] = value
                    simulator.state = replace(simulator.state, mode=1, channels=tuple(values))
                else:
                    simulator.state = replace(
                        simulator.state, mode=1 if operation == "manual" else 0
                    )
                if hook:
                    hook(operation, simulator, deadline)

        worker = ha.HAValidationWorker(
            config,
            TOKEN,
            service_factory=Service,
            session_factory=simulator.factory,
            clock=simulator.clock,
            sink=sink,
            sleeper=lambda seconds: simulator.clock.advance(seconds, float("inf")),
        )
        simulator.worker = worker
        result = worker.run()
        return result, simulator, calls

    def test_native_number_action_then_independent_tcp_cleanup(self):
        result, simulator, calls = self.run_worker()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(calls, [("channel", 9)])
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(len(simulator.writes), 3)
        self.assertLess(result["excursion_seconds"], 10)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_native_manual_and_automatic_services_without_any_channel_write(self):
        result, simulator, calls = self.run_worker("manual")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(calls, [("manual", None), ("automatic_program", None)])
        self.assertEqual(simulator.writes, [])
        self.assertEqual(simulator.state, simulator.original)

    def test_ha_completion_without_matching_tcp_state_never_passes(self):
        def ignored(operation, simulator, deadline):
            simulator.state = simulator.original

        result, simulator, calls = self.run_worker(hook=ignored)
        self.assertEqual(result["experiment"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(calls, [("channel", 9)])
        self.assertEqual(simulator.writes, [])

    def test_timeout_never_means_cancellation_or_confirmed_final_recovery(self):
        def timed_out(operation, simulator, deadline):
            simulator.clock.value = deadline
            raise ha.HACompletionUnknown("synthetic timeout while HA may continue")

        result, simulator, calls = self.run_worker(hook=timed_out)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(calls, [("channel", 9)])
        self.assertLess(result["excursion_seconds"], 10)
        stages = [event["stage"] for event in result["events"]]
        self.assertIn("original_state_observed_but_ha_completion_unknown", stages)
        wait = next(event for event in result["events"] if event["stage"] == "recovery_started")
        self.assertGreaterEqual(wait["excursion_seconds"], 3.25)

    def test_unknown_manual_delivery_never_queues_a_second_ha_mode_action(self):
        def timed_out(operation, simulator, deadline):
            simulator.clock.value = deadline
            raise ha.HACompletionUnknown("synthetic uncertain Manual service")

        result, simulator, calls = self.run_worker("manual", hook=timed_out)
        self.assertEqual(calls, [("manual", None)])
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual([command for _, command in simulator.writes], [base.mode_frame(0)])

    def test_signal_after_completed_ha_action_still_runs_local_guarded_cleanup(self):
        def stop(operation, simulator, deadline):
            simulator.worker.request_stop()

        result, simulator, calls = self.run_worker(hook=stop)
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(len(calls), 1)

    def test_competing_output_after_ha_action_is_not_overwritten(self):
        def competing(operation, simulator, deadline):
            simulator.state = replace(simulator.state, channels=(9, 20, 30, 40, 51, 60))

        result, simulator, _ = self.run_worker(hook=competing)
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(simulator.writes, [])
        self.assertEqual(simulator.state.channels[4], 51)

    def test_uncertain_ha_automatic_restore_is_observed_but_not_retried_or_claimed(self):
        def timeout_automatic(operation, simulator, deadline):
            if operation == "automatic_program":
                raise ha.HACompletionUnknown("synthetic lost HA Automatic completion")

        result, simulator, calls = self.run_worker("manual", hook=timeout_automatic)
        self.assertEqual(calls, [("manual", None), ("automatic_program", None)])
        self.assertEqual(result["recovery"], "FAIL")
        self.assertEqual(result["ha_completion"], "UNKNOWN")
        self.assertEqual(simulator.state, simulator.original)
        self.assertEqual(simulator.writes, [])
        self.assertLess(result["excursion_seconds"], 10)

    def test_ha_cleanup_requires_time_for_full_coordinator_deadline_before_dispatch(self):
        simulator = Simulator()
        service = Mock()
        worker = ha.HAValidationWorker(
            ha.Configuration.parse(ha_data("manual"), simulation=True),
            TOKEN,
            service_factory=lambda *_args: service,
            clock=simulator.clock,
        )
        worker.cleaning = True
        with self.assertRaises(base.DeadlineError):
            worker._ha_call(
                "automatic_program", None, simulator.clock() + 3, "restore_original_mode"
            )
        service.call.assert_not_called()

    def test_transient_tcp_readback_after_ha_automatic_only_retries_reads(self):
        failed = False

        def transient(operation, simulator, deadline):
            if operation != "automatic_program":
                return

            def fail_once(event, sim):
                nonlocal failed
                if event == "read" and not failed:
                    failed = True
                    raise ConnectionResetError("synthetic one-time post-HA read failure")

            simulator.hook = fail_once

        result, simulator, calls = self.run_worker("manual", hook=transient)
        self.assertTrue(failed)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(calls, [("manual", None), ("automatic_program", None)])
        self.assertEqual(simulator.writes, [])
        self.assertEqual(simulator.state, simulator.original)


class FakeHA:
    """Real HTTP socket with synthetic service effects and no secret-bearing logs."""

    def __init__(self, lamp, *, tcp_actuation=False):
        self.lamp = lamp
        self.tcp_actuation = tcp_actuation
        self.actuator_errors = []
        self.requests = []
        self.status = 200
        self.delay = 0
        self.effect_finished = threading.Event()
        service = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    self.request.settimeout(2)
                    data = bytearray()
                    while b"\r\n\r\n" not in data:
                        chunk = self.request.recv(1024)
                        if not chunk:
                            return
                        data.extend(chunk)
                    header, body = bytes(data).split(b"\r\n\r\n", 1)
                    lines = header.split(b"\r\n")
                    method, path, _ = lines[0].decode("ascii").split(" ")
                    headers = dict(line.decode("ascii").split(": ", 1) for line in lines[1:])
                    size = int(headers["Content-Length"])
                    while len(body) < size:
                        body += self.request.recv(1024)
                    payload = json.loads(body[:size])
                    service.requests.append(
                        (method, path, payload, headers["Authorization"] == f"Bearer {TOKEN}")
                    )
                    if service.delay:
                        time.sleep(service.delay)
                    status = service.status
                    if status == 200:
                        if service.tcp_actuation:
                            try:
                                service.actuate_tcp(path, payload)
                            except (base.ValidationError, OSError, EOFError) as error:
                                service.actuator_errors.append(type(error).__name__)
                                status = 500
                        else:
                            service.actuate_state(path, payload)
                        service.effect_finished.set()
                    response = (
                        f"HTTP/1.1 {status} Synthetic\r\n"
                        "Location: http://example.invalid/never-follow\r\n"
                        "Content-Length: 32\r\nConnection: close\r\n\r\n"
                        "synthetic-sensitive-error-body"
                    ).encode("ascii")
                    self.request.sendall(response)
                except (ConnectionError, socket.timeout):
                    return

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def actuate_state(self, path, payload):
        with self.lamp.lock:
            if path == "/api/services/number/set_value":
                channels = list(self.lamp.state["channels"])
                channels[0] = payload["value"]
                self.lamp.state.update(channels=tuple(channels), mode=1)
            elif path == "/api/services/select/select_option":
                self.lamp.state["mode"] = 1 if payload["option"] == "manual" else 0

    def actuate_tcp(self, path, payload):
        """Synthetic HA handler uses its own real TCP client and queried readback."""
        worker = base.ValidationWorker(self.config().device)
        deadline = time.monotonic() + 2.5
        try:
            before = worker._read(deadline, fresh=True)
            if path == "/api/services/number/set_value":
                channels = list(before.channels)
                channels[0] = payload["value"]
                channels, mode = tuple(channels), 1
            else:
                channels = None
                mode = 1 if payload["option"] == "manual" else 0
            after = worker._command(channels, mode, deadline, "synthetic_ha")
            if after.mode != mode or (channels is not None and after.channels != channels):
                raise base.UnsafeState("synthetic HA actuator readback mismatch")
        finally:
            worker._close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def config(self, action="channel"):
        data = ha_data(action)
        data["device"]["port"] = self.lamp.port
        data["ha"]["origin"] = f"http://127.0.0.1:{self.server.server_address[1]}"
        return ha.Configuration.parse(data, simulation=True)


class ExclusiveLoopbackDevice(LoopbackDevice):
    """Only one TCP handler may process frames until its current client closes."""

    def __init__(self):
        super().__init__()
        self.owner = threading.Lock()
        self.rejected_connections = 0
        handler = self.server.RequestHandlerClass
        device = self

        class ExclusiveHandler(handler):
            def handle(self):
                # Permit EOF handling on a just-closed connection to finish;
                # a retained observer instead makes the second client fail.
                if not device.owner.acquire(timeout=0.3):
                    with device.lock:
                        device.rejected_connections += 1
                    return
                try:
                    super().handle()
                finally:
                    device.owner.release()

        self.server.RequestHandlerClass = ExclusiveHandler


class ExclusiveHAHandoffTests(unittest.TestCase):
    def test_number_releases_observer_before_native_http_tcp_actuation(self):
        with ExclusiveLoopbackDevice() as lamp, FakeHA(lamp, tcp_actuation=True) as service:
            result = ha.HAValidationWorker(service.config(), TOKEN).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["ha_completion"], "HTTP_COMPLETED")
        self.assertEqual(service.actuator_errors, [])
        self.assertEqual(lamp.rejected_connections, 0)
        self.assertEqual(lamp.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
        writes = [command for command in lamp.observed if command[2] == 0xFA]
        self.assertEqual(
            writes,
            [
                base.channel_frame((9, 20, 30, 40, 50, 60), service.config().device.controller),
                base.mode_frame(1),
                base.channel_frame((10, 20, 30, 40, 50, 60), service.config().device.controller),
                base.mode_frame(1),
                base.mode_frame(0),
            ],
        )
        self.assertLess(result["excursion_seconds"], 10)

    def test_manual_and_automatic_cleanup_each_release_tcp_observer(self):
        with ExclusiveLoopbackDevice() as lamp, FakeHA(lamp, tcp_actuation=True) as service:
            result = ha.HAValidationWorker(service.config("manual"), TOKEN).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["ha_completion"], "HTTP_COMPLETED")
        self.assertEqual(service.actuator_errors, [])
        self.assertEqual(lamp.rejected_connections, 0)
        self.assertEqual(
            [request[2]["option"] for request in service.requests], ["manual", "automatic_program"]
        )
        self.assertEqual(
            [command for command in lamp.observed if command[2] == 0xFA],
            [base.mode_frame(1), base.mode_frame(0)],
        )
        self.assertEqual(lamp.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})
        self.assertLess(result["excursion_seconds"], 10)

    def test_retained_read_only_client_blocks_other_tcp_actuator_without_mutation(self):
        with ExclusiveLoopbackDevice() as lamp, FakeHA(lamp, tcp_actuation=True) as service:
            config = service.config()
            observer = base.WireSession(config.device, time.monotonic() + 1)
            try:
                before = observer.read_state(time.monotonic() + 1)
                with self.assertRaises(ha.HACompletionUnknown):
                    ha.HAService(config, TOKEN).call("channel", 9, time.monotonic() + 1)
                self.assertEqual(observer.read_state(time.monotonic() + 1), before)
            finally:
                observer.close()
        self.assertEqual(lamp.rejected_connections, 1)
        self.assertEqual(len(service.actuator_errors), 1)
        self.assertIn(service.actuator_errors[0], ("EOFError", "ConnectionResetError"))
        self.assertTrue(
            all(command in (base.SYSTEM_QUERY, base.CHANNEL_QUERY) for command in lamp.observed)
        )


class NativeHATransportTests(unittest.TestCase):
    def test_full_native_http_number_and_independent_tcp_packet_readback(self):
        with LoopbackDevice() as lamp, FakeHA(lamp) as service:
            config = service.config()
            result = ha.HAValidationWorker(config, TOKEN).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(
            service.requests,
            [
                (
                    "POST",
                    "/api/services/number/set_value",
                    {"entity_id": "number.aquarius_plant_led_channel_a", "value": 9},
                    True,
                )
            ],
        )
        self.assertEqual(lamp.state, {"mode": 0, "channels": (10, 20, 30, 40, 50, 60)})

    def test_full_native_http_manual_then_automatic_without_tcp_channel_mutation(self):
        with LoopbackDevice() as lamp, FakeHA(lamp) as service:
            result = ha.HAValidationWorker(service.config("manual"), TOKEN).run()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(
            [request[2]["option"] for request in service.requests], ["manual", "automatic_program"]
        )
        self.assertFalse(any(command[2] == 0xFA for command in lamp.observed))
        self.assertEqual(lamp.state["mode"], 0)

    def test_error_and_redirect_bodies_are_never_exposed_or_followed(self):
        for status in (400, 401, 403, 404, 302, 500):
            with self.subTest(status=status), LoopbackDevice() as lamp, FakeHA(lamp) as service:
                service.status = status
                transport = ha.HAService(service.config(), TOKEN)
                with self.assertRaises(ha.HAServiceError) as error:
                    transport.call("channel", 9, time.monotonic() + 1)
                self.assertNotIn("sensitive", str(error.exception))
                self.assertNotIn(TOKEN, str(error.exception))
                self.assertEqual(len(service.requests), 1)
                self.assertEqual(lamp.state["channels"][0], 10)

    def test_timeout_does_not_cancel_the_synthetic_ha_service(self):
        with LoopbackDevice() as lamp, FakeHA(lamp) as service:
            service.delay = 0.2
            transport = ha.HAService(service.config(), TOKEN)
            started = time.monotonic()
            with self.assertRaises(ha.HACompletionUnknown):
                transport.call("channel", 9, started + 0.04)
            self.assertLess(time.monotonic() - started, 0.15)
            self.assertTrue(service.effect_finished.wait(1))
            self.assertEqual(lamp.state["channels"][0], 9)

    def test_transport_rejects_unconfigured_operations_before_any_http_request(self):
        with LoopbackDevice() as lamp, FakeHA(lamp) as service:
            transport = ha.HAService(service.config(), TOKEN)
            for action, value in (
                ("shutdown", None),
                ("channel", 101),
                ("channel", True),
                ("manual", 1),
            ):
                with self.assertRaises(ValueError):
                    transport.call(action, value, time.monotonic() + 1)
            self.assertEqual(service.requests, [])


class HAConfigurationTests(unittest.TestCase):
    def test_exact_private_origin_and_correct_aquarius_entities_are_required(self):
        for origin in (
            "http://8.8.8.8:8123",
            "http://example.invalid",
            "http://127.0.0.1:0",
            "http://" + "user:password" + "@127.0.0.1",
            "http://127.0.0.1/api",
            "ftp://127.0.0.1",
        ):
            data = ha_data()
            data["ha"]["origin"] = origin
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                ha.Configuration.parse(data, simulation=True)
        for key, value in (
            ("number_entity", "number.unrelated_control"),
            ("number_entity", "number.aquarius_plant_led_channel_b"),
            ("number_entity", ["number.aquarius_plant_led_channel_a"]),
            ("mode_entity", "select.unrelated_device"),
        ):
            data = ha_data()
            data["ha"][key] = value
            with self.assertRaises(ValueError):
                ha.Configuration.parse(data, simulation=True)

    def test_zero_delta_only_permitted_for_explicit_manual_action(self):
        data = ha_data()
        data["device"]["delta"] = 0
        with self.assertRaises(ValueError):
            ha.Configuration.parse(data, simulation=True)
        self.assertEqual(ha.Configuration.parse(ha_data("manual"), simulation=True).device.delta, 0)
        data = ha_data("manual")
        data["device"]["delta"] = -1
        with self.assertRaises(ValueError):
            ha.Configuration.parse(data, simulation=True)
        data = ha_data()
        data["restore_mode_via_ha"] = True
        with self.assertRaises(ValueError):
            ha.Configuration.parse(data, simulation=True)

    def test_token_is_memory_only_and_header_injection_is_rejected(self):
        for token in ("", "bad\r\nheader", "with space", "é", "x" * (ha.MAX_TOKEN_BYTES + 1)):
            with self.assertRaises(ValueError):
                ha._token(token)
        self.assertEqual(ha._token(TOKEN), TOKEN)

    def test_cli_reads_authorization_from_stdin_and_prints_only_status_fields(self):
        config = ha.Configuration.parse(ha_data(), simulation=True)
        worker = Mock()
        worker.run.return_value = {"status": "PASS", "experiment": "PASS", "recovery": "PASS"}
        output = io.StringIO()
        with (
            patch.object(ha, "_configuration", return_value=config),
            patch.object(ha.base, "PrivateReport", return_value=None),
            patch.object(ha, "HAValidationWorker", return_value=worker) as factory,
            patch.object(
                ha.sys, "stdin", SimpleNamespace(buffer=io.BytesIO((TOKEN + "\n").encode()))
            ),
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

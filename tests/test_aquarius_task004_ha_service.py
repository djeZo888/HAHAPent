"""Independent synthetic tests for fixed Task 004 HA service transport routes."""

import contextlib
import io
import json
import socket
import socketserver
import threading
import time
import unittest
from unittest.mock import Mock, patch

from tests.test_aquarius_validation import config_data
from tooling import aquarius_task004_ha_service as service

TOKEN = "synthetic-task004-in-memory-token"
BODY_MARKER = "synthetic-private-response-body"


def configuration(action="channel"):
    device = config_data()
    if action != "channel":
        device["delta"] = 0
    return {
        "schema_version": 1,
        "device": device,
        "action": action,
        "ha": {
            "origin": "http://127.0.0.1:8123",
            "number_entity": "number.aquarius_plant_led_channel_a",
            "light_entity": "light.aquarius_plant_led_lamp",
            "resume_entity": "button.aquarius_plant_led_resume_schedule",
        },
    }


class ConfigurationTests(unittest.TestCase):
    def test_only_explicit_private_ipv4_or_simulated_loopback(self):
        for origin in ("http://10.23.42.17", "https://172.20.23.17", "http://192.168.23.17:8123"):
            raw = configuration()
            raw["device"]["host"] = "192.168.23.18"
            raw["ha"]["origin"] = origin
            parsed = service.Configuration.parse(raw)
            self.assertIn(parsed.port, (80, 443, 8123))
        raw = configuration()
        raw["device"]["host"] = "192.168.23.18"
        with self.assertRaises(ValueError):
            service.Configuration.parse(raw)
        self.assertEqual(
            service.Configuration.parse(configuration(), simulation=True).host, "127.0.0.1"
        )

    def test_origin_rejects_alternate_destinations_userinfo_paths_and_non_strings(self):
        for origin in (
            "http://8.8.8.8",
            "http://lamp.example.invalid",
            "http://169.254.1.2",
            "http://[::1]",
            "http://127.0.0.1/path",
            "http://127.0.0.1?x=1",
            "http://127.0.0.1#fragment",
            "http://" + "user:password" + "@127.0.0.1",
            "ftp://127.0.0.1",
            "http://127.0.0.1:0",
            "http://127.0.0.1:65536",
            None,
            [],
            7,
        ):
            raw = configuration()
            raw["ha"]["origin"] = origin
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                service.Configuration.parse(raw, simulation=True)

    def test_exact_config_shape_version_and_action_delta(self):
        for field, value in (("schema_version", True), ("schema_version", 2), ("action", "off")):
            raw = configuration()
            raw[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                service.Configuration.parse(raw, simulation=True)
        raw = configuration()
        raw["ha"]["extra"] = "not allowed"
        with self.assertRaises(ValueError):
            service.Configuration.parse(raw, simulation=True)
        for action in ("power_manual", "power_automatic", "resume_program"):
            for delta in (-1, 1, True, 0.0):
                raw = configuration(action)
                raw["device"]["delta"] = delta
                with self.subTest(action=action, delta=delta), self.assertRaises(ValueError):
                    service.Configuration.parse(raw, simulation=True)

    def test_exact_entity_families_and_selected_channel_only(self):
        for key, value in (
            ("number_entity", "number.aquarius_plant_led_channel_b"),
            ("number_entity", "number.aquarius_plant_led_channel_a_0"),
            ("light_entity", "light.unrelated"),
            ("light_entity", "light.aquarius_plant_led_lamp\r\nX: 1"),
            ("resume_entity", "button.unrelated"),
        ):
            raw = configuration()
            raw["ha"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                service.Configuration.parse(raw, simulation=True)
        raw = configuration()
        for key in ("number_entity", "light_entity", "resume_entity"):
            raw["ha"][key] += "_2"
        self.assertEqual(
            service.Configuration.parse(raw, simulation=True).light_entity,
            raw["ha"]["light_entity"],
        )


class ServiceTests(unittest.TestCase):
    def make_service(self, action="channel"):
        return service.Service(
            service.Configuration.parse(configuration(action), simulation=True), TOKEN
        )

    def socket(self, chunks=None):
        connection = Mock()
        connection.recv.side_effect = chunks or [b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"]
        return connection

    def test_routes_only_send_exact_entity_and_required_scalar(self):
        for configured, action, value, path, expected in (
            (
                "channel",
                "channel",
                11,
                "number/set_value",
                {"entity_id": "number.aquarius_plant_led_channel_a", "value": 11},
            ),
            (
                "power_manual",
                "off",
                None,
                "light/turn_off",
                {"entity_id": "light.aquarius_plant_led_lamp"},
            ),
            (
                "power_manual",
                "on",
                None,
                "light/turn_on",
                {"entity_id": "light.aquarius_plant_led_lamp"},
            ),
            (
                "power_automatic",
                "off",
                None,
                "light/turn_off",
                {"entity_id": "light.aquarius_plant_led_lamp"},
            ),
            (
                "resume_program",
                "resume",
                None,
                "button/press",
                {"entity_id": "button.aquarius_plant_led_resume_schedule"},
            ),
        ):
            connection = self.socket()
            with (
                self.subTest(action=action, configured=configured),
                patch.object(
                    service.socket, "create_connection", return_value=connection
                ) as connect,
            ):
                self.assertIsNone(
                    self.make_service(configured).call(action, value, time.monotonic() + 1)
                )
                request = connection.sendall.call_args.args[0]
                header, body = request.split(b"\r\n\r\n", 1)
                self.assertTrue(
                    header.startswith(f"POST /api/services/{path} HTTP/1.1\r\n".encode())
                )
                self.assertEqual(json.loads(body), expected)
                self.assertIn(f"Content-Length: {len(body)}".encode(), header)
                self.assertIn(f"Authorization: Bearer {TOKEN}".encode(), header)
                self.assertEqual(connect.call_args.args[0], ("127.0.0.1", 8123))
                connect.assert_called_once()
                connection.close.assert_called_once()

    def test_transaction_cannot_call_another_route(self):
        permitted = {
            "channel": {"channel"},
            "power_manual": {"off", "on"},
            "power_automatic": {"off", "on"},
            "resume_program": {"resume"},
        }
        with patch.object(service.socket, "create_connection") as connect:
            for configured, allowed in permitted.items():
                for action in {"channel", "off", "on", "resume", "brightness", "manual"} - allowed:
                    with (
                        self.subTest(configured=configured, action=action),
                        self.assertRaises(ValueError),
                    ):
                        self.make_service(configured).call(action, None, time.monotonic() + 1)
            connect.assert_not_called()

    def test_power_has_no_brightness_color_or_extra_service_data(self):
        with patch.object(service.socket, "create_connection") as connect:
            for value in (0, 1, 100, False, {"brightness": 10}, {"rgb_color": [1, 2, 3]}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.make_service("power_manual").call("on", value, time.monotonic() + 1)
            for value in (-1, 101, True, 1.0, "10", None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.make_service().call("channel", value, time.monotonic() + 1)
            connect.assert_not_called()

    def test_rejections_are_completed_failure_without_body_disclosure(self):
        for status in (400, 401, 403, 404):
            body = f"{BODY_MARKER} {TOKEN}".encode()
            connection = self.socket([f"HTTP/1.1 {status} Rejected\r\n\r\n".encode() + body])
            output = io.StringIO()
            with (
                patch.object(service.socket, "create_connection", return_value=connection),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(output),
            ):
                with self.assertRaises(service.HAServiceError) as raised:
                    self.make_service().call("channel", 11, time.monotonic() + 1)
            self.assertNotIsInstance(raised.exception, service.HACompletionUnknown)
            self.assertNotIn(TOKEN, str(raised.exception) + output.getvalue())
            self.assertNotIn(BODY_MARKER, str(raised.exception) + output.getvalue())
            connection.close.assert_called_once()

    def test_server_errors_redirects_bad_status_and_eof_are_unknown_and_not_retried(self):
        responses = (
            b"HTTP/1.1 500 Internal Error\r\n\r\n",
            b"HTTP/1.1 302 Found\r\nLocation: http://8.8.8.8/\r\n\r\n",
            b"HTTP/2 200 OK\r\n\r\n",
            b"not HTTP\r\n\r\n",
            b"",
            b"HTTP/1.1 200 OK\r\nX: " + b"a" * 17000,
        )
        for response in responses:
            connection = self.socket([response])
            with (
                self.subTest(response=response[:20]),
                patch.object(
                    service.socket, "create_connection", return_value=connection
                ) as connect,
            ):
                with self.assertRaises(service.HACompletionUnknown):
                    self.make_service().call("channel", 11, time.monotonic() + 1)
                connect.assert_called_once()
                connection.close.assert_called_once()

    def test_partial_send_timeout_and_read_timeout_are_unknown(self):
        for stage in ("sendall", "recv"):
            connection = self.socket()
            getattr(connection, stage).side_effect = socket.timeout(f"{TOKEN} {BODY_MARKER}")
            with patch.object(service.socket, "create_connection", return_value=connection):
                with self.assertRaises(service.HACompletionUnknown) as raised:
                    self.make_service().call("channel", 11, time.monotonic() + 1)
            self.assertNotIn(TOKEN, str(raised.exception))
            self.assertNotIn(BODY_MARKER, str(raised.exception))
            connection.close.assert_called_once()

    def test_connection_failure_and_expired_deadline_do_not_deliver(self):
        with patch.object(
            service.socket, "create_connection", side_effect=OSError(TOKEN)
        ) as connect:
            with self.assertRaises(service.HAServiceError) as raised:
                self.make_service().call("channel", 11, time.monotonic() + 1)
            self.assertNotIsInstance(raised.exception, service.HACompletionUnknown)
            self.assertNotIn(TOKEN, str(raised.exception))
            connect.assert_called_once()
        with patch.object(service.socket, "create_connection") as connect:
            with self.assertRaises(service.HAServiceError):
                self.make_service().call("channel", 11, time.monotonic() - 1)
            connect.assert_not_called()

    def test_token_is_memory_only_and_cannot_inject_headers(self):
        parsed = service.Configuration.parse(configuration(), simulation=True)
        for token in ("", "x\r\nHeader: injected", "x y", "x" * 8193, None):
            with (
                self.subTest(token_length=len(token) if token else 0),
                self.assertRaises(ValueError),
            ):
                service.Service(parsed, token)


class LoopbackHTTP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, effect_delay=0):
        self.requests = []
        self.effect = threading.Event()
        self.effect_delay = effect_delay
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(1)
                data = b""
                while b"\r\n\r\n" not in data:
                    data += self.request.recv(1024)
                head, body = data.split(b"\r\n\r\n", 1)
                length = int(
                    next(
                        line.split(b":", 1)[1]
                        for line in head.split(b"\r\n")
                        if line.lower().startswith(b"content-length:")
                    )
                )
                while len(body) < length:
                    body += self.request.recv(1024)
                owner.requests.append((head.split(b"\r\n", 1)[0], json.loads(body)))
                if owner.effect_delay:
                    time.sleep(owner.effect_delay)
                    owner.effect.set()
                try:
                    self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n[]")
                except OSError:
                    pass

        super().__init__(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=1)


class RealLoopbackTransportTests(unittest.TestCase):
    def test_http200_is_completion_only_without_a_physical_state_result(self):
        server = LoopbackHTTP()
        try:
            raw = configuration("power_manual")
            raw["ha"]["origin"] = f"http://127.0.0.1:{server.server_address[1]}"
            actuator = service.Service(service.Configuration.parse(raw, simulation=True), TOKEN)
            self.assertIsNone(actuator.call("off", None, time.monotonic() + 1))
            self.assertEqual(
                server.requests,
                [
                    (
                        b"POST /api/services/light/turn_off HTTP/1.1",
                        {"entity_id": raw["ha"]["light_entity"]},
                    )
                ],
            )
            self.assertFalse(server.effect.is_set())
        finally:
            server.close()

    def test_http_timeout_cannot_cancel_a_later_server_effect(self):
        server = LoopbackHTTP(effect_delay=0.1)
        try:
            raw = configuration("power_manual")
            raw["ha"]["origin"] = f"http://127.0.0.1:{server.server_address[1]}"
            actuator = service.Service(service.Configuration.parse(raw, simulation=True), TOKEN)
            with self.assertRaises(service.HACompletionUnknown):
                actuator.call("off", None, time.monotonic() + 0.03)
            self.assertTrue(server.effect.wait(1))
            self.assertEqual(len(server.requests), 1)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()

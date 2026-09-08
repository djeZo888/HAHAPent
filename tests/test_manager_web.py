"""HTTP, Ingress and lifecycle contracts with synthetic users and engine only."""

import http.client
import json
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from manager.hahapent.ha import HAError
from manager.hahapent.server import (
    Application,
    IngressServer,
    WebError,
    authorize,
    public_error,
    strict_json,
)

USER = "a" * 32


def headers(**changes):
    result = Message()
    data = {
        "X-Remote-User-Id": USER,
        "Host": "ha.example:8123",
        "Origin": "http://ha.example:8123",
        "X-HAHAPent-Request": "1",
        **changes,
    }
    for key, value in data.items():
        if value is not None:
            result[key] = value
    return result


class IngressAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.ha = MagicMock()
        self.ha.is_admin.return_value = True

    def test_actual_gateway_and_active_admin_allowed(self):
        authorize("172.30.32.2", headers(), self.ha, mutation=True)
        self.ha.is_admin.assert_called_once_with(USER)

    def test_spoofed_headers_do_not_override_socket_peer(self):
        for peer in ("127.0.0.1", "172.30.33.1", "10.0.0.2", "::ffff:172.30.32.2"):
            with self.assertRaises(WebError):
                authorize(peer, headers(**{"X-Forwarded-For": "172.30.32.2"}), self.ha)
        self.ha.is_admin.assert_not_called()

    def test_missing_duplicate_and_nonadmin_id_denied(self):
        missing = headers(**{"X-Remote-User-Id": None})
        duplicate = headers()
        duplicate["X-Remote-User-Id"] = USER
        for request_headers in (missing, duplicate):
            with self.assertRaises(WebError):
                authorize("172.30.32.2", request_headers, self.ha)
        self.ha.is_admin.return_value = False
        with self.assertRaises(WebError):
            authorize("172.30.32.2", headers(), self.ha)

    def test_cross_origin_null_missing_csrf_and_forged_fetch_site_denied(self):
        for changes in (
            {"Origin": "https://evil.example"},
            {"Origin": "null"},
            {"Origin": None},
            {"Origin": "http://" + "ha.example:8123@evil.example"},
            {"X-HAHAPent-Request": None},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            with self.subTest(changes=changes), self.assertRaises(WebError):
                authorize("172.30.32.2", headers(**changes), self.ha, mutation=True)

    def test_duplicate_host_origin_and_csrf_denied(self):
        for header in ("Host", "Origin", "X-HAHAPent-Request"):
            request_headers = headers()
            request_headers[header] = request_headers[header]
            with self.assertRaises(WebError):
                authorize("172.30.32.2", request_headers, self.ha, mutation=True)

    def test_outage_denies_even_previously_authorized_user(self):
        authorize("172.30.32.2", headers(), self.ha)
        self.ha.is_admin.side_effect = HAError()
        with self.assertRaises(HAError):
            authorize("172.30.32.2", headers(), self.ha)


class RequestContractTests(unittest.TestCase):
    def setUp(self):
        self.manager = MagicMock()
        self.manager.operation = {"state": "idle"}
        self.app = Application(self.manager, MagicMock())

    def finish(self):
        deadline = time.monotonic() + 2
        while self.app.job()["state"] == "running" and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertNotEqual(self.app.job()["state"], "running")

    def test_json_rejects_duplicate_keys_arrays_nonfinite_and_bad_utf8(self):
        for raw in (b'{"x":1,"x":2}', b"[]", b'{"x":NaN}', b'{"x":Infinity}', b"\xff"):
            with self.assertRaises(WebError):
                strict_json(raw)

    def test_unsafe_action_arguments_and_missing_confirmation_rejected(self):
        for operation, body in (
            ("remove", {"domain": "demo", "confirmed": False}),
            ("rollback", {"domain": "demo", "confirmed": False}),
            ("source_add", {"repository_url": "https://github.com/example/demo", "trusted": False}),
            ("test_mode", {"enabled": 1}),
            ("restart", {}),
            (
                "install",
                {"source_id": "demo", "module_id": "demo", "version": "1.0.0", "script": "bad"},
            ),
        ):
            with self.subTest(operation=operation), self.assertRaises(WebError):
                self.app.submit(operation, body)
        self.assertEqual(self.manager.mock_calls, [])

    def test_source_add_remove_are_never_code_operations(self):
        self.app.submit(
            "source_add", {"repository_url": "https://github.com/example/demo", "trusted": True}
        )
        self.finish()
        self.manager.add_source.assert_called_once_with(
            "https://github.com/example/demo", trusted=True
        )
        self.app.submit("source_remove", {"source_id": "demo"})
        self.finish()
        self.manager.remove_source.assert_called_once_with("demo")
        self.manager.install.assert_not_called()
        self.manager.remove.assert_not_called()

    def test_job_progress_and_serialization(self):
        release = threading.Event()
        self.manager.install.side_effect = lambda *args: release.wait(2)
        self.manager.operation = {"phase": "staging"}
        try:
            self.app.submit(
                "install", {"source_id": "demo", "module_id": "demo", "version": "1.0.0"}
            )
            self.assertEqual(self.app.job()["phase"], "staging")
            with self.assertRaises(WebError):
                self.app.submit("refresh", {})
        finally:
            release.set()
        self.finish()
        self.assertEqual(self.app.job()["state"], "complete")

    def test_remove_native_config_guard_error_is_visible_without_raw_error(self):
        class GuardError(Exception):
            code = "remove_native_config_entries_first"

        self.manager.remove.side_effect = GuardError("private HA response must not escape")
        self.app.submit("remove", {"domain": "demo", "confirmed": True})
        self.finish()
        result = self.app.job()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Home Assistant first", result["error"]["message"])
        self.assertNotIn("private", json.dumps(result))

    def test_arbitrary_exception_and_error_code_are_sanitized(self):
        error = RuntimeError("private response")
        error.code = "private/response-token"
        self.assertEqual(public_error(error)["code"], "operation_failed")


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.manager = MagicMock()
        self.manager.operation = {"state": "idle"}
        self.manager.status.return_value = {
            "modules": [],
            "installed": [],
            "settings": {},
            "sources": [],
        }
        self.ha = MagicMock()
        self.ha.is_admin.return_value = True
        self.server = IngressServer(("127.0.0.1", 0), Application(self.manager, self.ha))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def request(self, path="/api/status", method="GET", body=None, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        request_headers = {
            "X-Remote-User-Id": USER,
            "Host": "ha.example:8123",
            "Origin": "http://ha.example:8123",
            "X-HAHAPent-Request": "1",
            "Content-Type": "application/json",
            **(extra or {}),
        }
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_real_socket_with_forged_identity_and_forwarded_peer_is_denied(self):
        for path, method, body in (
            ("/", "GET", None),
            ("/api/status", "GET", None),
            ("/api/install", "POST", b"{}"),
        ):
            result = self.request(path, method, body, {"X-Forwarded-For": "172.30.32.2"})
            self.assertEqual(result[0], 403)
        self.ha.is_admin.assert_not_called()
        self.manager.status.assert_not_called()
        self.manager.install.assert_not_called()

    @patch("manager.hahapent.server.TRUSTED_INGRESS", "127.0.0.1")
    def test_admin_page_and_api_use_csp_no_cors_and_current_roles(self):
        result = self.request("/")
        self.assertEqual(result[0], 200)
        self.assertIn(b"Suite Manager", result[2])
        self.assertIn("script-src 'self'", result[1]["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", result[1])
        self.assertEqual(result[1]["Cache-Control"], "no-store")
        self.ha.is_admin.return_value = False
        self.assertEqual(self.request()[0], 403)

    @patch("manager.hahapent.server.TRUSTED_INGRESS", "127.0.0.1")
    def test_post_json_and_origin_checks_precede_mutation(self):
        for extra, body, status in (
            ({"Origin": "https://evil.example"}, b"{}", 403),
            ({"Content-Type": "text/plain"}, b"{}", 400),
            ({}, b'{"x":1,"x":2}', 400),
            ({}, b"x" * 17000, 413),
        ):
            self.assertEqual(self.request("/api/refresh", "POST", body, extra)[0], status)
        self.manager.refresh_catalogs.assert_not_called()

    @patch("manager.hahapent.server.TRUSTED_INGRESS", "127.0.0.1")
    def test_authenticated_mutation_runs_exact_engine_action(self):
        result = self.request("/api/remove", "POST", b'{"domain":"demo","confirmed":true}')
        self.assertEqual(result[0], 202)
        deadline = time.monotonic() + 2
        while not self.manager.remove.called and time.monotonic() < deadline:
            time.sleep(0.005)
        self.manager.remove.assert_called_once_with("demo", confirmed=True)

    @patch("manager.hahapent.server.TRUSTED_INGRESS", "127.0.0.1")
    def test_path_traversal_and_no_restart_service_endpoint(self):
        for path in ("/../ha.py", "/%2e%2e/ha.py", "/app.js?debug=1", "/health"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request("/api/restart", "POST", b"{}")[0], 400)


class FrontendContractTests(unittest.TestCase):
    def test_untrusted_catalog_uses_dom_text_and_validated_links(self):
        script = Path("manager/hahapent/static/app.js").read_text()
        for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write"):
            self.assertNotIn(unsafe, script)
        self.assertIn("textContent", script)
        self.assertIn('url.protocol !== "https:"', script)
        self.assertIn("noopener noreferrer", script)

    def test_lifecycle_ui_native_config_and_separate_test_catalog(self):
        script = Path("manager/hahapent/static/app.js").read_text()
        page = Path("manager/hahapent/static/index.html").read_text()
        for action in (
            'perform("install"',
            'perform("rollback"',
            'perform("remove"',
            'perform("test_mode"',
        ):
            self.assertIn(action, script)
        self.assertIn("/config/integrations/dashboard/add?domain=", script)
        self.assertIn("cannot undo", script)
        self.assertIn("Device-free test catalog", page)
        self.assertNotIn('id="test-mode" type="checkbox" checked', page)

    def test_removed_restart_reminder_uses_persisted_recovery_rows(self):
        script = Path("manager/hahapent/static/app.js").read_text()
        page = Path("manager/hahapent/static/index.html").read_text()
        self.assertIn("removedRows.some((row) => row.restart_pending)", script)
        self.assertIn("including after the Manager restarts", script)
        self.assertIn("Removed-code reminders stay with retained backups", page)

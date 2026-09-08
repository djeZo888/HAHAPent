"""Synthetic Core responses only; never reads the protected project profile."""

import json
import unittest
from unittest.mock import MagicMock, patch

from manager.hahapent.ha import HAError, HomeAssistant, _BudgetSocket

USER = "a" * 32


def user(**changes):
    return {
        "id": USER,
        "is_active": True,
        "is_owner": False,
        "system_generated": False,
        "group_ids": ["system-admin"],
        **changes,
    }


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.ha = HomeAssistant("synthetic-app-credential")
        self.command = MagicMock(return_value=[user()])
        self.ha._command = self.command

    def test_active_admin_and_owner_allowed_roles_checked_every_time(self):
        self.assertTrue(self.ha.is_admin(USER))
        self.command.return_value = [user(group_ids=[], is_owner=True)]
        self.assertTrue(self.ha.is_admin(USER))
        self.command.return_value = [user(group_ids=[])]
        self.assertFalse(self.ha.is_admin(USER))
        self.assertEqual(self.command.call_count, 3)
        self.command.assert_called_with("config/auth/list")

    def test_inactive_system_missing_duplicate_and_nonadmin_denied(self):
        for rows in (
            [user(is_active=False)],
            [user(system_generated=True)],
            [user(group_ids=["system-users"])],
            [],
            [user(), user()],
        ):
            with self.subTest(rows=rows):
                self.command.return_value = rows
                self.assertFalse(self.ha.is_admin(USER))

    def test_invalid_identity_does_not_call_ha(self):
        for identity in ("", "administrator", "../user", USER + "," + USER, None):
            self.assertFalse(self.ha.is_admin(identity))
        self.command.assert_not_called()

    def test_malformed_roles_cannot_grant_administrator(self):
        for groups in ("prefix-system-admin", {"system-admin": True}, None, [1]):
            self.command.return_value = [user(group_ids=groups)]
            self.assertFalse(self.ha.is_admin(USER))

    def test_authorization_outage_fails_closed(self):
        self.command.side_effect = HAError()
        with self.assertRaises(HAError):
            self.ha.is_admin(USER)

    def test_unknown_user_response_fails_closed(self):
        self.command.return_value = {"users": [user()]}
        with self.assertRaises(HAError):
            self.ha.is_admin(USER)


class CoreReadTests(unittest.TestCase):
    def setUp(self):
        self.ha = HomeAssistant("synthetic-app-credential")

    def test_version_excludes_configuration(self):
        self.ha._command = MagicMock(return_value={"version": "2026.9.1", "private": "discard"})
        self.assertEqual(self.ha.core_version(), "2026.9.1")
        self.ha._command.assert_called_once_with("get_config")

    def test_entries_requested_by_domain_and_sensitive_fields_removed(self):
        self.ha._command = MagicMock(
            return_value=[
                {
                    "domain": "hahapent_test",
                    "entry_id": "synthetic",
                    "state": "loaded",
                    "title": "Do not return",
                    "data": {"private": "discard"},
                }
            ]
        )
        result = self.ha.config_entries("hahapent_test")
        self.assertEqual(
            result, [{"domain": "hahapent_test", "entry_id": "synthetic", "state": "loaded"}]
        )
        self.ha._command.assert_called_once_with("config_entries/get", domain="hahapent_test")

    def test_wrong_domain_response_and_invalid_request_rejected(self):
        self.ha._command = MagicMock(return_value=[{"domain": "unrelated"}])
        with self.assertRaises(HAError):
            self.ha.config_entries("hahapent_test")
        with self.assertRaises(HAError):
            self.ha.config_entries("../escape")

    def test_domain_validation_matches_published_contract(self):
        self.ha._command = MagicMock(return_value=[])
        self.assertEqual(self.ha.config_entries("a" * 100), [])
        with self.assertRaises(HAError):
            self.ha.config_entries("a" * 101)

    def test_builtin_and_builtin_override_are_conflicts(self):
        for builtin, overwrites, expected in (
            (True, False, True),
            (False, True, True),
            (False, False, False),
        ):
            self.ha._command = MagicMock(
                return_value={
                    "domain": "demo",
                    "is_built_in": builtin,
                    "overwrites_built_in": overwrites,
                }
            )
            self.assertEqual(self.ha.is_core_domain("demo"), expected)

    def test_missing_domain_is_different_from_ha_failure(self):
        self.ha._command = MagicMock(side_effect=HAError("ha_not_found"))
        self.assertFalse(self.ha.is_core_domain("hahapent_test"))
        self.ha._command.side_effect = HAError("ha_unavailable")
        with self.assertRaises(HAError):
            self.ha.is_core_domain("hahapent_test")

    def test_manifest_missing_ownership_flags_cannot_allow_install(self):
        self.ha._command = MagicMock(return_value={"domain": "demo"})
        with self.assertRaises(HAError):
            self.ha.is_core_domain("demo")

    def test_loaded_version_requires_loaded_config_entry(self):
        self.ha.config_entries = MagicMock(return_value=[{"state": "loaded"}])
        self.ha._manifest = MagicMock(return_value={"version": "1.0.0"})
        self.assertEqual(
            self.ha.domain_status("demo"),
            {
                "configured": True,
                "loaded": True,
                "loaded_version": "1.0.0",
                "config_entry_count": 1,
            },
        )
        self.ha._manifest.reset_mock()
        self.ha.config_entries.return_value = [{"state": "setup_error"}]
        status = self.ha.domain_status("demo")
        self.assertTrue(status["configured"])
        self.assertFalse(status["loaded"])
        self.assertIsNone(status["loaded_version"])
        self.ha._manifest.assert_not_called()


class TransportTests(unittest.TestCase):
    @patch("manager.hahapent.ha.websocket.create_connection")
    @patch("manager.hahapent.ha.socket.create_connection")
    def test_fixed_proxy_handshake_and_readonly_command(self, socket_connect, ws_connect):
        connection = ws_connect.return_value
        connection.recv.side_effect = [
            json.dumps(value)
            for value in (
                {"type": "auth_required"},
                {"type": "auth_ok"},
                {"id": 1, "type": "result", "success": True, "result": {"version": "2026.9.1"}},
            )
        ]
        self.assertEqual(HomeAssistant("synthetic-app-credential").core_version(), "2026.9.1")
        socket_connect.assert_called_once_with(("supervisor", 80), 8)
        self.assertEqual(ws_connect.call_args.args[0], "ws://supervisor/core/websocket")
        self.assertEqual(ws_connect.call_args.kwargs["redirect_limit"], 0)
        sent = [json.loads(call.args[0]) for call in connection.send.call_args_list]
        self.assertEqual(sent[1], {"id": 1, "type": "get_config"})
        connection.close.assert_called_once()

    @patch("manager.hahapent.ha.socket.create_connection")
    def test_no_token_never_opens_network(self, connect):
        with self.assertRaises(HAError):
            HomeAssistant("").core_version()
        connect.assert_not_called()

    @patch("manager.hahapent.ha.websocket.create_connection")
    @patch("manager.hahapent.ha.socket.create_connection")
    def test_auth_failure_is_sanitized(self, socket_connect, ws_connect):
        ws_connect.side_effect = RuntimeError("synthetic-secret-response-body")
        with self.assertRaises(HAError) as caught:
            HomeAssistant("synthetic-app-credential").core_version()
        self.assertEqual(str(caught.exception), "ha_unavailable")
        socket_connect.return_value.close.assert_called_once()

    def test_receive_budget_rejects_oversize_frames(self):
        stream = MagicMock()
        stream.recv.return_value = b"four"
        bounded = _BudgetSocket(stream)
        bounded.remaining = 3
        with self.assertRaises(HAError):
            bounded.recv(2000)
        stream.recv.assert_called_once_with(4)

    def test_exchange_deadline_bounds_slow_peer(self):
        bounded = _BudgetSocket(MagicMock())
        bounded.deadline = 0
        with self.assertRaises(HAError):
            bounded.recv(1)

"""Only synthetic credentials, responses, sockets, and temporary private files."""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tooling import check_access as access_cli
from tooling import git_credential
from tooling.access import (
    EXPECTED_REPOSITORY,
    AccessClient,
    AccessError,
    BoundedSocket,
    HAWebSocket,
    Profile,
    check_access,
    load_private_profile,
    parse_credentials,
    read_private_file,
)

SYNTHETIC_HOST = "192.168.0.2"
SYNTHETIC_TOKEN = "synthetic-github-fixture"
SYNTHETIC_HA_TOKEN = "synthetic-ha-fixture"


def credential_text(password: str = "synthetic:pass\\word ") -> str:
    return (
        f"GitHub URL: https://github.com/{EXPECTED_REPOSITORY}\n"
        f"GitHub API token: {SYNTHETIC_TOKEN}\n"
        f"HomeAssistant IP: {SYNTHETIC_HOST}\n"
        "HomeAssistant username: synthetic-user\n"
        f"HomeAssistant password: {password}\n"
        f"HomeAssistant token: {SYNTHETIC_HA_TOKEN}\n"
    )


def profile(**kwargs):
    arguments = {
        "github_repository": EXPECTED_REPOSITORY,
        "ha_host": SYNTHETIC_HOST,
        "credential_file": Path("/synthetic-private/credentials.txt"),
        "credentials": parse_credentials(credential_text()),
    }
    arguments.update(kwargs)
    return Profile(**arguments)


class ParserTests(unittest.TestCase):
    def test_first_colon_backslashes_crlf_and_meaningful_whitespace(self):
        password = " leading:colons:\\and\\slashes\t "
        actual = parse_credentials(credential_text(password).replace("\n", "\r\n"))
        self.assertEqual(actual.ha_password, password)
        self.assertEqual(actual.github_token, SYNTHETIC_TOKEN)

    def test_no_separator_space_is_preserved(self):
        text = credential_text().replace("password: ", "password:")
        self.assertEqual(parse_credentials(text).ha_password, "synthetic:pass\\word ")

    def test_case_and_label_spacing(self):
        text = credential_text().replace("GitHub API token", "  github   API  TOKEN ")
        self.assertEqual(parse_credentials(text).github_token, SYNTHETIC_TOKEN)

    def test_missing_duplicate_unknown_placeholder_and_controls(self):
        invalid = [
            "\n".join(credential_text().splitlines()[:-1]),
            credential_text() + "GitHub API token: duplicate\n",
            credential_text() + "Unknown: secret-value\n",
            credential_text().replace(SYNTHETIC_TOKEN, "<YOUR_TOKEN>"),
            credential_text().replace(SYNTHETIC_TOKEN, "change_me"),
            credential_text().replace(SYNTHETIC_TOKEN, "  "),
            credential_text().replace(SYNTHETIC_TOKEN, "hidden\rheader"),
            credential_text().replace(SYNTHETIC_TOKEN, "hidden\x00value"),
        ]
        for text in invalid:
            with self.subTest(case=invalid.index(text)), self.assertRaises(AccessError) as context:
                parse_credentials(text)
            self.assertEqual(str(context.exception), "credentials_invalid")
            self.assertNotIn("secret-value", repr(context.exception))

    def test_secret_containers_have_redacted_repr(self):
        self.assertNotIn(SYNTHETIC_TOKEN, repr(profile()))
        self.assertNotIn(SYNTHETIC_TOKEN, repr(profile().credentials))
        self.assertEqual(str(AccessError(SYNTHETIC_TOKEN)), "request_failed")


class PrivateFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hahapent-synthetic-")
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.credentials = self.root / "credentials.txt"
        self.credentials.write_text(credential_text(), encoding="utf-8")
        self.credentials.chmod(0o600)
        self.profile_file = self.root / "bootstrap.json"
        self.write_profile()

    def tearDown(self):
        self.temporary.cleanup()

    def write_profile(self, **extra):
        data = {
            "github_repository": EXPECTED_REPOSITORY,
            "ha_host": SYNTHETIC_HOST,
            "credential_file": str(self.credentials),
            "ha_expected_username": "synthetic-user",
            "ha_url": f"http://{SYNTHETIC_HOST}:8123",
        }
        data.update(extra)
        self.profile_file.write_text(json.dumps(data), encoding="utf-8")
        self.profile_file.chmod(0o600)

    def test_external_private_profile_resolves(self):
        result = load_private_profile(self.profile_file)
        self.assertEqual(result.credentials.ha_token, SYNTHETIC_HA_TOKEN)
        self.assertEqual(result.ha_url, f"http://{SYNTHETIC_HOST}:8123")

    def test_file_permissions_rejected(self):
        self.credentials.chmod(0o644)
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            load_private_profile(self.profile_file)

    def test_private_directory_permissions_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            load_private_profile(self.profile_file)

    def test_symlink_hardlink_and_fifo_rejected(self):
        link = self.root / "linked.txt"
        link.symlink_to(self.credentials)
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            read_private_file(link)
        link.unlink()
        os.link(self.credentials, link)
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            read_private_file(self.credentials)
        link.unlink()
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            read_private_file(fifo)

    def test_any_worktree_and_explicit_root_rejected(self):
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            read_private_file(self.credentials, worktree_roots=(self.root,))
        (self.root / ".git").write_text("gitdir: synthetic\n", encoding="utf-8")
        with self.assertRaisesRegex(AccessError, "private_file_rejected"):
            read_private_file(self.credentials)

    def test_non_worktree_parent_cwd_does_not_block_durable_profile(self):
        with patch("tooling.access.Path.cwd", return_value=self.root):
            self.assertEqual(load_private_profile(self.profile_file).ha_host, SYNTHETIC_HOST)

    def test_profile_duplicate_keys_and_username_mismatch_rejected(self):
        self.profile_file.write_text('{"ha_host":"a","ha_host":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(AccessError, "profile_invalid"):
            load_private_profile(self.profile_file)
        self.write_profile(ha_expected_username="different-synthetic-user")
        with self.assertRaisesRegex(AccessError, "profile_invalid"):
            load_private_profile(self.profile_file)

    def test_private_profile_ssh_metadata_is_validated_without_reading_key(self):
        self.write_profile(
            ha_ssh_key=str(self.root / "future-key"),
            ha_ssh_known_hosts=str(self.root / "future-known-hosts"),
            ha_ssh_port=2222,
        )
        loaded = load_private_profile(self.profile_file)
        self.assertEqual(loaded.ha_ssh_port, 2222)
        self.assertEqual(loaded.ha_ssh_key, self.root / "future-key")
        self.assertFalse(loaded.ha_ssh_key.exists())
        self.write_profile(ha_config_dir="/etc")
        with self.assertRaisesRegex(AccessError, "profile_invalid"):
            load_private_profile(self.profile_file)


class TargetTests(unittest.TestCase):
    def test_other_repository_or_host_rejected(self):
        synthetic_userinfo = ":".join(("name", "pass"))
        for arguments in (
            {"github_repository": "someone/else"},
            {"ha_host": "192.168.0.3"},
            {"ha_host": "127.0.0.1"},
            {"ha_host": "8.8.8.8"},
            {"ha_url": "https://other.invalid:8123"},
            {"ha_url": f"http://{SYNTHETIC_HOST}:8123/path"},
            {"ha_url": f"http://{synthetic_userinfo}@{SYNTHETIC_HOST}:8123"},
            {"ha_url": f"http://{SYNTHETIC_HOST}:8123#fragment"},
            {"ha_url": f"http://{SYNTHETIC_HOST}:22"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(AccessError):
                profile(**arguments)

    def test_github_url_exact_origin_and_path(self):
        for url in (
            f"http://github.com/{EXPECTED_REPOSITORY}",
            f"https://github.com.evil.invalid/{EXPECTED_REPOSITORY}",
            f"https://name@github.com/{EXPECTED_REPOSITORY}",
            f"https://github.com/{EXPECTED_REPOSITORY}?secret=1",
        ):
            credentials = parse_credentials(
                credential_text().replace(f"https://github.com/{EXPECTED_REPOSITORY}", url)
            )
            with self.assertRaisesRegex(AccessError, "target_rejected"):
                profile(credentials=credentials)

    def test_unauthenticated_origin_identification_required(self):
        client = AccessClient(profile())
        with self.assertRaisesRegex(AccessError, "target_rejected"):
            client.get("ha", "/api/", authenticated=True)
        with self.assertRaisesRegex(AccessError, "target_rejected"):
            client.websocket()

    def test_non_allowlisted_endpoints_rejected_before_connection(self):
        client = AccessClient(profile())
        client.ha_identified = True
        with patch("tooling.access._connect") as connect:
            for service, path in (
                ("github", "/repos/someone/else"),
                ("ha", "/api/states"),
                ("ha", "/api/config?token=anything"),
                ("ha", "//other.invalid/api/"),
            ):
                with self.assertRaisesRegex(AccessError, "target_rejected"):
                    client.get(service, path, authenticated=True)
            connect.assert_not_called()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = AccessClient(profile())
        self.connect = patch("tooling.access._connect")
        self.connect.start()
        self.connection_patch = patch("tooling.access.http.client.HTTPConnection")
        self.connection = self.connection_patch.start().return_value
        self.response = self.connection.getresponse.return_value

    def tearDown(self):
        self.connect.stop()
        self.connection_patch.stop()

    def test_redirect_rejected_and_body_not_read(self):
        for status in (301, 302, 303, 307, 308):
            self.response.status = status
            with self.assertRaisesRegex(AccessError, "redirect_rejected"):
                self.client.get("github", "/user", authenticated=True)
        self.response.read.assert_not_called()

    def test_http_error_and_exception_do_not_leak(self):
        self.response.status = 401
        self.response.read.return_value = SYNTHETIC_TOKEN.encode()
        with self.assertRaisesRegex(AccessError, "http_rejected"):
            self.client.get("github", "/user", authenticated=True)
        self.response.read.assert_not_called()
        self.connection.getresponse.side_effect = RuntimeError(SYNTHETIC_TOKEN)
        with self.assertRaises(AccessError) as context:
            self.client.get("github", "/user", authenticated=True)
        self.assertNotIn(SYNTHETIC_TOKEN, str(context.exception))

    def test_read_only_request_contract(self):
        self.response.status = 200
        self.response.read.return_value = b'{"login":"synthetic"}'
        self.assertEqual(self.client.get("github", "/user", True), {"login": "synthetic"})
        arguments = self.connection.request.call_args
        self.assertEqual(arguments.args, ("GET", "/user"))
        self.assertEqual(arguments.kwargs["headers"]["Authorization"], "Bearer " + SYNTHETIC_TOKEN)

    def test_frontend_identification_has_no_authorization_header(self):
        self.response.status = 200
        self.response.read.side_effect = [b"{}", b"<home-assistant></home-assistant>"]
        self.client.identify_ha()
        self.assertTrue(self.client.ha_identified)
        self.assertEqual(self.connection.request.call_count, 2)
        for call in self.connection.request.call_args_list:
            self.assertNotIn("Authorization", call.kwargs["headers"])

    def test_provider_redirect_does_not_fall_back(self):
        self.response.status = 302
        with self.assertRaisesRegex(AccessError, "redirect_rejected"):
            self.client.identify_ha()
        self.assertFalse(self.client.ha_identified)
        self.assertEqual(self.connection.request.call_count, 1)


class BoundedSocketTests(unittest.TestCase):
    def test_byte_budget_applies_to_http_file_reads(self):
        stream = MagicMock()
        stream.recv.return_value = b"123456"
        bounded = BoundedSocket(stream, time.monotonic() + 10, byte_limit=5)
        with self.assertRaisesRegex(AccessError, "response_too_large"):
            bounded.makefile("rb").read(10000)
        self.assertEqual(stream.recv.call_args.args[0], 6)

    def test_deadline_checked_before_recv_and_send(self):
        bounded = BoundedSocket(MagicMock(), time.monotonic() - 1)
        with self.assertRaisesRegex(AccessError, "request_timeout"):
            bounded.recv(1)
        with self.assertRaisesRegex(AccessError, "request_timeout"):
            bounded.send(b"synthetic")
        bounded.stream.recv.assert_not_called()

    def test_http_adapter_works_with_real_local_socketpair_only(self):
        left, right = socket.socketpair()
        try:
            right.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
            import http.client

            response = http.client.HTTPResponse(BoundedSocket(left, time.monotonic() + 2))
            response.begin()
            self.assertEqual(response.read(), b"{}")
        finally:
            left.close()
            right.close()


class WebSocketTests(unittest.TestCase):
    def setUp(self):
        self.identity_patch = patch("tooling.access.AccessClient.identify_ha")
        self.identity = self.identity_patch.start()
        self.socket_patch = patch("tooling.access._connect")
        self.socket_patch.start()
        self.ws_patch = patch("websocket.WebSocket")
        self.ws = self.ws_patch.start().return_value
        self.ws.getstatus.return_value = 101
        self.ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]

    def tearDown(self):
        self.identity_patch.stop()
        self.socket_patch.stop()
        self.ws_patch.stop()

    def test_handshake_auth_and_read_only_command_contract(self):
        self.ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({"id": 1, "type": "result", "success": True, "result": {"is_admin": True}}),
        ]
        with HAWebSocket(profile()) as connection:
            self.assertEqual(connection.command("auth/current_user"), {"is_admin": True})
            with self.assertRaisesRegex(AccessError, "target_rejected"):
                connection.command("call_service")
        self.assertEqual(self.ws.connect.call_args.kwargs["redirect_limit"], 0)
        self.identity.assert_called_once()
        self.assertEqual(json.loads(self.ws.send.call_args_list[0].args[0])["type"], "auth")
        self.assertEqual(
            json.loads(self.ws.send.call_args_list[1].args[0]),
            {"id": 1, "type": "auth/current_user"},
        )
        self.ws.shutdown.assert_called_once()

    def test_redirect_status_rejected_before_token(self):
        self.ws.getstatus.return_value = 302
        with self.assertRaisesRegex(AccessError, "redirect_rejected"):
            with HAWebSocket(profile()):
                self.fail("redirect accepted")
        self.ws.send.assert_not_called()
        self.ws.recv.assert_not_called()

    def test_auth_rejection_and_command_failure_never_echo_messages(self):
        self.ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_invalid", "message": SYNTHETIC_HA_TOKEN}),
        ]
        with self.assertRaises(AccessError) as context:
            with HAWebSocket(profile()):
                self.fail("auth accepted")
        self.assertEqual(str(context.exception), "authentication_rejected")


class ReportTests(unittest.TestCase):
    def test_only_allowlisted_evidence_leaves_report(self):
        client = MagicMock()
        client.get.side_effect = [
            {"login": "private-user", "id": "private-id", "token": SYNTHETIC_TOKEN},
            {"full_name": EXPECTED_REPOSITORY, "permissions": {"push": True}},
            {"message": "API running."},
            {
                "version": "2026.9.1",
                "latitude": 12.34,
                "longitude": 23.45,
                "location_name": "private-home",
            },
        ]
        client.websocket.return_value.__enter__.return_value.command.side_effect = [
            {"id": "private-id", "name": "private-user", "is_admin": True, "is_owner": False},
            {"location_name": "private-home", "entities": ["private-device"]},
            [{"id": "private-id", "name": "private-user"}],
        ]
        report = check_access(profile(), client)
        encoded = json.dumps(report)
        for excluded in (SYNTHETIC_TOKEN, SYNTHETIC_HOST, "private-", "latitude", "entities"):
            self.assertNotIn(excluded, encoded)
        self.assertEqual(
            report["facts"],
            {"ha_core_version": "2026.9.1", "ha_is_owner": False, "ha_is_admin": True},
        )
        self.assertEqual(report["checks"]["github_write"]["status"], "AVAILABLE_NOT_EXERCISED")
        self.assertEqual(report["checks"]["ha_write"]["status"], "NOT_TESTED")
        self.assertEqual(report["checks"]["ha_token_username_binding"]["status"], "NOT_TESTED")
        self.assertEqual(report["checks"]["ha_password_login"]["status"], "NOT_TESTED")
        self.assertEqual(report["checks"]["ha_administrator_read"]["status"], "PASS")

    def test_injected_exceptions_never_reach_report(self):
        client = MagicMock()
        client.get.side_effect = RuntimeError(SYNTHETIC_TOKEN)
        client.identify_ha.side_effect = RuntimeError(SYNTHETIC_HA_TOKEN)
        encoded = json.dumps(check_access(profile(), client))
        self.assertNotIn(SYNTHETIC_TOKEN, encoded)
        self.assertNotIn(SYNTHETIC_HA_TOKEN, encoded)


class GitHelperTests(unittest.TestCase):
    def test_git_challenge_arrays_and_inherited_username_do_not_choose_target(self):
        request = (
            "capability[]=authtype\n"
            "capability[]=state\n"
            "protocol=https\n"
            "host=github.com\n"
            f"path={EXPECTED_REPOSITORY}.git\n"
            "username=synthetic-inherited-user\n"
            'wwwauth[]=Basic realm="synthetic"\n'
            "wwwauth[]=Bearer synthetic-challenge\n\n"
        )
        self.assertTrue(git_credential._request_matches(request))
        self.assertFalse(git_credential._request_matches(request.replace("https", "http")))
        self.assertFalse(
            git_credential._request_matches(request.replace("github.com", "other.invalid"))
        )
        self.assertFalse(
            git_credential._request_matches(request.replace(EXPECTED_REPOSITORY, "other/repo"))
        )
        self.assertFalse(git_credential._request_matches(request + "host=github.com\n"))
        self.assertFalse(git_credential._request_matches(request + "credential=synthetic\n"))

    def test_protocol_host_path_and_duplicates(self):
        valid = f"protocol=https\nhost=github.com\npath={EXPECTED_REPOSITORY}.git\n\n"
        self.assertTrue(git_credential._request_matches(valid))
        for request in (
            valid.replace("https", "http"),
            valid.replace("github.com", "github.com.evil.invalid"),
            valid.replace(EXPECTED_REPOSITORY, "someone/else"),
            "protocol=https\nhost=github.com\n",
            valid + "host=github.com\n",
            valid + "password=synthetic\n",
        ):
            self.assertFalse(git_credential._request_matches(request))

    def test_direct_invocation_refused_without_reading_secret(self):
        with (
            patch("tooling.git_credential._git_invocation", return_value=False),
            patch("tooling.git_credential.load_private_profile") as load,
            patch("sys.stdout", new_callable=io.StringIO) as output,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            self.assertEqual(git_credential.main(["get"]), 1)
            self.assertEqual(output.getvalue(), "")
            load.assert_not_called()

    def test_git_only_protocol_output_and_no_storage(self):
        request = (
            f"protocol=https\nhost=github.com\npath={EXPECTED_REPOSITORY}\n"
            "username=synthetic-inherited-user\nwwwauth[]=synthetic-challenge\n\n"
        )
        with (
            patch("tooling.git_credential._git_invocation", return_value=True),
            patch("tooling.git_credential.load_private_profile", return_value=profile()) as load,
            patch("sys.stdin", io.StringIO(request)),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(git_credential.main(["get"]), 0)
            self.assertEqual(
                output.getvalue(), f"username=x-access-token\npassword={SYNTHETIC_TOKEN}\n\n"
            )
            load.assert_called_once()
            load.reset_mock()
            self.assertEqual(git_credential.main(["store"]), 0)
            self.assertEqual(git_credential.main(["erase"]), 0)
            load.assert_not_called()


class CLITests(unittest.TestCase):
    def test_ssh_and_file_probe_are_explicit_opt_ins(self):
        ssh_module = types.ModuleType("tooling.ssh_access")
        ssh_module.check_ssh = MagicMock(return_value={})
        for arguments, expected in (([], None), (["--ssh"], False), (["--file-probe"], True)):
            with (
                self.subTest(arguments=arguments),
                patch.dict(sys.modules, {"tooling.ssh_access": ssh_module}),
                patch("tooling.check_access.load_private_profile", return_value=profile()),
                patch(
                    "tooling.check_access.check_access", return_value={"checks": {}, "facts": {}}
                ),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                ssh_module.check_ssh.reset_mock()
                access_cli.main(arguments)
                report = json.loads(output.getvalue())
                if expected is None:
                    ssh_module.check_ssh.assert_not_called()
                    self.assertNotIn("ssh", report)
                else:
                    self.assertEqual(
                        ssh_module.check_ssh.call_args.kwargs, {"file_probe": expected}
                    )
                    self.assertEqual(report["ssh"]["ssh_session"], "BLOCKED")

    def test_ssh_report_is_filtered_and_failures_set_exit_status(self):
        ssh_module = types.ModuleType("tooling.ssh_access")
        ssh_module.check_ssh = MagicMock(
            return_value={"ssh_session": "PASS", "ha_cli": "FAIL", "private_data": SYNTHETIC_TOKEN}
        )
        with (
            patch.dict(sys.modules, {"tooling.ssh_access": ssh_module}),
            patch("tooling.check_access.load_private_profile", return_value=profile()),
            patch("tooling.check_access.check_access", return_value={"checks": {}, "facts": {}}),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(access_cli.main(["--ssh"]), 1)
            self.assertNotIn(SYNTHETIC_TOKEN, output.getvalue())
            self.assertNotIn("private_data", output.getvalue())


if __name__ == "__main__":
    unittest.main()

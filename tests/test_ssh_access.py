"""Synthetic SSH protocol/subprocess tests; no live host or private file access."""

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tooling.access import Credentials, Profile
from tooling.ssh_access import CHECKS, MAX_OUTPUT, PROBE_SCRIPT, READ_ONLY_SCRIPT, _run, check_ssh


def synthetic_profile():
    return Profile(
        github_repository="djeZo888/HAHAPent",
        ha_host="192.168.50.10",
        credential_file=Path("/synthetic/private/credentials.txt"),
        credentials=Credentials(
            "https://github.com/djeZo888/HAHAPent",
            "synthetic-token",
            "192.168.50.10",
            "synthetic-user",
            "synthetic-pass",
            "synthetic-ha-token",
        ),
        ha_ssh_key=Path("/synthetic/.config/hahapent/secrets/key"),
        ha_ssh_known_hosts=Path("/synthetic/.config/hahapent/known_hosts"),
        ha_ssh_port=2222,
    )


def protocol(file_probe=False):
    values = dict.fromkeys(CHECKS, "PASS")
    if not file_probe:
        values.update(file_probe="NOT_REQUIRED", file_probe_cleanup="NOT_REQUIRED")
    return "".join(name + "=" + status + "\n" for name, status in values.items()).encode()


class SSHContractTests(unittest.TestCase):
    def setUp(self):
        self.profile = synthetic_profile()
        self.home = patch("tooling.ssh_access.Path.home", return_value=Path("/synthetic"))
        self.private = patch("tooling.ssh_access.read_private_file", return_value="synthetic")
        self.home.start()
        self.private_mock = self.private.start()
        self.addCleanup(self.home.stop)
        self.addCleanup(self.private.stop)

    def test_strict_args_and_default_read_only_script(self):
        with patch("tooling.ssh_access._run", return_value=protocol()) as run:
            report = check_ssh(self.profile)
        args, script = run.call_args.args
        self.assertEqual(report["ssh_session"], "PASS")
        self.assertEqual(report["file_probe"], "NOT_REQUIRED")
        self.assertEqual(args[:4], ["/usr/bin/ssh", "-F", "/dev/null", "-T"])
        for option in (
            "BatchMode=yes",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "IdentityAgent=none",
            "UpdateHostKeys=no",
            "GlobalKnownHostsFile=/dev/null",
            "ForwardAgent=no",
            "ClearAllForwardings=yes",
            "PermitLocalCommand=no",
            "ProxyCommand=none",
            "ProxyJump=none",
        ):
            self.assertIn(option, args)
        self.assertEqual(args[-3:], ["--", "root@192.168.50.10", "sh -s"])
        self.assertEqual(args[args.index("-p") + 1], "2222")
        self.assertEqual(args[args.index("-i") + 1], str(self.profile.ha_ssh_key))
        self.assertIn("UserKnownHostsFile=" + str(self.profile.ha_ssh_known_hosts), args)
        self.assertIn(b"readlink -f /config", script)
        self.assertIn(b"ha core info >/dev/null", script)
        self.assertIn(b"ha supervisor info >/dev/null", script)
        for mutation in (b"mktemp", b"mkdir", b"rm ", b"restart", b"reboot"):
            self.assertNotIn(mutation, script)
        self.assertEqual(self.private_mock.call_count, 2)

    def test_explicit_probe_is_narrow_and_has_cleanup_traps(self):
        with patch("tooling.ssh_access._run", return_value=protocol(True)) as run:
            report = check_ssh(self.profile, file_probe=True)
        script = run.call_args.args[1].decode()
        self.assertEqual(report["file_probe_cleanup"], "PASS")
        self.assertIn('mktemp -d "$resolved/.hahapent-task001.XXXXXXXXXX"', script)
        self.assertIn("umask 077", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("trap 'exit 1' HUP INT TERM", script)
        self.assertIn('cmp -s - "$probe_dir/marker"', script)
        self.assertIn('[ ! -x "$probe_dir/marker" ]', script)
        self.assertIn('rm -f -- "$probe_dir/marker" && rmdir -- "$probe_dir"', script)
        for forbidden in ("rm -r", "configuration.yaml", ".storage", "knx", "restart", "reboot"):
            self.assertNotIn(forbidden, script)

    def test_absent_components_do_not_create_a_package_or_report_write_test(self):
        output = protocol().replace(
            b"custom_components_directory=PASS",
            b"custom_components_directory=AVAILABLE_NOT_EXERCISED",
        )
        with patch("tooling.ssh_access._run", return_value=output) as run:
            report = check_ssh(self.profile)
        self.assertEqual(report["custom_components_directory"], "AVAILABLE_NOT_EXERCISED")
        script = run.call_args.args[1]
        self.assertIn(b'[ ! -e "$components" ] && [ ! -L "$components" ]', script)
        self.assertNotIn(b"mkdir", script)

    def test_invalid_profile_data_is_rejected_before_subprocess(self):
        for field, value in (
            ("ha_host", "192.168.50.10; synthetic-injection"),
            ("ha_ssh_port", "22; synthetic-injection"),
            ("ha_config_dir", "/config; synthetic-injection"),
            ("ha_ssh_key", Path("/synthetic/elsewhere/key")),
            ("ha_ssh_known_hosts", Path("/synthetic/.config/hahapent/host keys")),
        ):
            with self.subTest(field=field):
                profile = synthetic_profile()
                object.__setattr__(profile, field, value)
                with patch("tooling.ssh_access._run") as run:
                    self.assertEqual(check_ssh(profile)["ssh_session"], "BLOCKED")
                run.assert_not_called()

    def test_private_file_failure_prevents_subprocess(self):
        self.private_mock.side_effect = ValueError("DO-NOT-ECHO")
        with patch("tooling.ssh_access._run") as run:
            report = check_ssh(self.profile)
        run.assert_not_called()
        self.assertNotIn("DO-NOT-ECHO", str(report))
        self.assertEqual(report["ssh_session"], "BLOCKED")

    def test_remote_failures_do_not_echo_or_infer_cleanup(self):
        failures = (
            TimeoutError("DO-NOT-ECHO"),
            subprocess.CalledProcessError(255, "DO-NOT-ECHO", output=b"DO-NOT-ECHO"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with patch("tooling.ssh_access._run", side_effect=failure):
                    report = check_ssh(self.profile, file_probe=True)
                self.assertEqual(report["file_probe_cleanup"], "BLOCKED")
                self.assertNotIn("DO-NOT-ECHO", str(report))

    def test_only_complete_allowlisted_protocol_is_accepted(self):
        for output in (
            b"DO-NOT-ECHO\n",
            protocol() + b"ssh_session=PASS\n",
            protocol().replace(b"ssh_session=PASS", b"ssh_session=DO-NOT-ECHO"),
            protocol().replace(b"file_probe_cleanup=NOT_REQUIRED\n", b""),
            protocol(True),
        ):
            with self.subTest(output_length=len(output)):
                with patch("tooling.ssh_access._run", return_value=output):
                    report = check_ssh(self.profile)
                self.assertEqual(report["ssh_session"], "BLOCKED")
                self.assertNotIn("DO-NOT-ECHO", str(report))

    def test_non_boolean_probe_is_not_authorization(self):
        with patch("tooling.ssh_access._run") as run:
            self.assertEqual(check_ssh(self.profile, file_probe="yes")["ssh_session"], "BLOCKED")
        run.assert_not_called()


class BoundedSubprocessTests(unittest.TestCase):
    def test_process_io_is_bounded_and_stderr_discarded(self):
        process = MagicMock()
        process.stdin.fileno.return_value = 10
        process.stdout.fileno.return_value = 11
        process.wait.return_value = 0
        process.poll.return_value = 0
        selector = MagicMock()
        selector.__enter__.return_value = selector
        selector.get_map.side_effect = [True, True, True, False]
        selector.select.side_effect = [
            [(SimpleNamespace(fileobj=process.stdin), 2)],
            [(SimpleNamespace(fileobj=process.stdout), 1)],
            [(SimpleNamespace(fileobj=process.stdout), 1)],
        ]
        with (
            patch("tooling.ssh_access.subprocess.Popen", return_value=process) as popen,
            patch("tooling.ssh_access.selectors.DefaultSelector", return_value=selector),
            patch("tooling.ssh_access.os.set_blocking"),
            patch("tooling.ssh_access.os.write", return_value=6),
            patch("tooling.ssh_access.os.read", side_effect=[b"result", b""]) as read,
        ):
            self.assertEqual(_run(["synthetic-ssh"], b"script"), b"result")
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertLessEqual(read.call_args_list[0].args[1], MAX_OUTPUT + 1)
        process.stdin.close.assert_called()
        process.kill.assert_not_called()

    def test_timeout_or_excess_output_kills_local_process(self):
        for oversized in (False, True):
            with self.subTest(oversized=oversized):
                process = MagicMock()
                process.poll.return_value = None
                selector = MagicMock()
                selector.__enter__.return_value = selector
                selector.select.return_value = (
                    [(SimpleNamespace(fileobj=process.stdout), 1)] if oversized else []
                )
                with (
                    patch("tooling.ssh_access.subprocess.Popen", return_value=process),
                    patch("tooling.ssh_access.selectors.DefaultSelector", return_value=selector),
                    patch("tooling.ssh_access.os.set_blocking"),
                    patch("tooling.ssh_access.os.read", return_value=b"X" * (MAX_OUTPUT + 1)),
                ):
                    with self.assertRaises((TimeoutError, ValueError)):
                        _run(["synthetic-ssh"], b"script")
                process.kill.assert_called_once()
                process.wait.assert_called_once_with(timeout=2)

    def test_scripts_remain_small_fixed_programs(self):
        self.assertLess(len((READ_ONLY_SCRIPT + PROBE_SCRIPT).encode()), 4096)


if __name__ == "__main__":
    unittest.main()

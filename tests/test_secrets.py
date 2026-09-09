"""Synthetic checks for the publication guard."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tooling import check_secrets
from tooling.check_secrets import inspect_blob


class SecretChecks(unittest.TestCase):
    def test_forbidden_operational_files(self):
        for name in (
            "credentials.txt",
            ".env.local",
            "backups/recovery.zip",
            "home/.storage/core.config",
            "project.knxproj",
            "trace.pcapng",
            "device.local.json",
            "camera.local.json",
            "camera-test.local.json",
            "private_evidence/analysis.md",
            "vendor.xapk",
            "vendor.apk",
            "classes.dex",
        ):
            with self.subTest(name=name):
                self.assertIn("forbidden_path", inspect_blob(name, b"ordinary"))

    def test_actual_values_and_patterns_are_detected(self):
        synthetic = b"synthetic-password-with-colon:a\\b "
        self.assertIn("private_value", inspect_blob("README.md", synthetic, (synthetic,)))
        token = b"ghp_" + b"X" * 36
        self.assertIn("github_token", inspect_blob("config.py", token))
        key = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----"
        self.assertIn("private_key", inspect_blob("config.py", key))

    def test_private_camera_capability_links_are_not_publishable(self):
        share = b"https://monitor.ui.com/" + b"11111111-2222-3333-4444-555555555555"
        for value in (share, share.upper(), share.replace(b"https:", b"http:")):
            with self.subTest(value=value):
                self.assertIn("private_camera_share", inspect_blob("notes.md", value))
                self.assertIn("private_camera_share", inspect_blob("notes.example", value))
        self.assertEqual(inspect_blob("docs.md", b"https://monitor.ui.com/"), [])

    def test_examples_do_not_bypass_value_scans(self):
        self.assertEqual(inspect_blob(".env.example", b"TOKEN=<placeholder>"), [])
        value = b"synthetic-private-value"
        self.assertIn("private_value", inspect_blob(".env.example", value, (value,)))

    def test_source_and_synthetic_metadata_are_allowed(self):
        for name in ("AGENTS.md", "tests/test_access.py", "tests/fixtures/catalog-valid.json"):
            self.assertEqual(inspect_blob(name, b"sanitized documentation"), [])

    def test_secrets_in_filenames_are_detected(self):
        synthetic = b"synthetic-private-value"
        self.assertIn(
            "private_value",
            inspect_blob("notes/" + synthetic.decode() + ".txt", b"ordinary", (synthetic,)),
        )
        token = "ghp_" + "X" * 36
        self.assertIn("github_token", inspect_blob("notes/" + token, b"ordinary"))


class GitObjectChecks(unittest.TestCase):
    """Exercise actual object reachability with an isolated, synthetic repository."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hahapent-synthetic-git-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = dict(os.environ)
        for key in tuple(environment):
            if key.startswith("GIT_"):
                del environment[key]
        environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.environment = environment
        self.run_git("init", "--template=", "--initial-branch=main")
        self.root_patch = patch.object(check_secrets, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.environment_patch = patch.dict(os.environ, environment, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def run_git(self, *arguments):
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Synthetic Fixture",
                "-c",
                "user.email=synthetic@example.invalid",
                "-c",
                "core.hooksPath=" + os.devnull,
                *arguments,
            ],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            check=True,
            timeout=15,
        )
        return result.stdout.decode().strip()

    def write(self, path, text="ordinary synthetic content\n"):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)

    def commit(self, message="Synthetic fixture commit"):
        self.run_git("add", "--all")
        self.run_git("commit", "-m", message)
        return self.run_git("rev-parse", "HEAD")

    def scan(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = check_secrets.main([*arguments, "--no-private-values"])
        return result, json.loads(output.getvalue())

    def assert_finding(self, arguments, category):
        result, report = self.scan(*arguments)
        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(category in item["categories"] for item in report["findings"]))
        # Reports must not disclose filenames, fixture contents, or object hashes.
        self.assertTrue(
            all(set(item) == {"object_number", "categories"} for item in report["findings"])
        )

    def test_outgoing_scans_existing_blob_at_new_forbidden_path(self):
        self.write("safe.txt")
        base = self.commit()
        self.run_git("mv", "safe.txt", "credentials.txt")
        self.commit()
        self.assert_finding(["--outgoing", base], "forbidden_path")

    def test_history_scans_all_aliases_of_identical_blob(self):
        self.write("safe.txt")
        self.write("backups/recovery.txt")
        self.commit()
        self.assert_finding(["--history"], "forbidden_path")

    def test_history_preserves_tab_and_newline_in_paths(self):
        self.write("logs/a\tb\nc.txt")
        self.commit()
        self.assert_finding(["--history"], "forbidden_path")

    def test_history_scans_removed_blob(self):
        token = "ghp_" + "X" * 36
        self.write("safe.txt", token)
        self.commit()
        self.run_git("rm", "safe.txt")
        self.commit()
        self.assert_finding(["--history"], "github_token")

    def test_history_scans_raw_commit_message(self):
        self.write("safe.txt")
        self.commit("ghp_" + "X" * 36)
        self.assert_finding(["--history"], "github_token")

    def test_history_does_not_allow_replace_refs_to_hide_commit_content(self):
        self.write("safe.txt")
        original = self.commit("ghp_" + "X" * 36)
        self.run_git("commit", "--amend", "-m", "Synthetic replacement")
        replacement = self.run_git("rev-parse", "HEAD")
        self.run_git("update-ref", "refs/heads/original", original)
        self.run_git("replace", original, replacement)
        self.assert_finding(["--history"], "github_token")

    def test_history_rejects_shallow_boundary(self):
        self.write("safe.txt")
        head = self.commit()
        (self.root / ".git/shallow").write_text(head + "\n")
        result, report = self.scan("--history")
        self.assertEqual(result, 2)
        self.assertEqual(report["status"], "BLOCKED")

    def test_history_scans_annotated_tag_message(self):
        self.write("safe.txt")
        self.commit()
        token = "ghp_" + "X" * 36
        self.run_git("tag", "-a", "synthetic-tag", "-m", token)
        self.assert_finding(["--history"], "github_token")

    def test_staged_symlink_scans_link_text_without_following(self):
        token = "ghp_" + "X" * 36
        (self.root / "link").symlink_to(token)
        self.run_git("add", "link")
        self.assert_finding(["--staged"], "github_token")

    def test_outgoing_rejects_missing_base_without_false_pass(self):
        self.write("safe.txt")
        self.commit()
        result, report = self.scan("--outgoing", "missing-base")
        self.assertEqual(result, 2)
        self.assertEqual(report["status"], "BLOCKED")

    def test_synthetic_clean_history_passes(self):
        self.write("safe.txt")
        self.commit()
        result, report = self.scan("--history")
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertGreater(report["objects_scanned"], 0)


if __name__ == "__main__":
    unittest.main()

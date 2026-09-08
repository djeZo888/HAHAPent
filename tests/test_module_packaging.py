"""Exercise native release archives using isolated synthetic Git repositories."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from manager.hahapent.downloads import extract_artifact
from tooling.build_module import ZIP_TIMESTAMP, build_artifact


class NativeModulePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.source = self.repository / "modules/synthetic_led/custom_components/synthetic_led"
        self.source.mkdir(parents=True)
        self.manifest = {
            "domain": "synthetic_led",
            "name": "Synthetic LED",
            "version": "0.1.0",
            "config_flow": True,
            "requirements": [],
        }
        self.write_manifest()
        (self.source / "__init__.py").write_text('"""Synthetic native integration."""\n')
        (self.source / "config_flow.py").write_text('"""Synthetic config flow."""\n')
        (self.source / "translations").mkdir()
        (self.source / "translations/en.json").write_text('{"config": {}}\n')
        self.git("init", "--quiet")
        self.revision = self.commit()

    def git(self, *arguments):
        # No remote, user config, hooks or signing is used in these temporary repos.
        return (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repository),
                    "-c",
                    "user.name=Synthetic Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *arguments,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            .stdout.decode()
            .strip()
        )

    def commit(self):
        self.git("add", "--", "modules")
        self.git("commit", "--quiet", "-m", "Synthetic package fixture")
        return self.git("rev-parse", "HEAD")

    def write_manifest(self):
        (self.source / "manifest.json").write_text(json.dumps(self.manifest) + "\n")

    def build(self, directory="artifacts", revision=None):
        return build_artifact(
            "synthetic_led", revision or self.revision, self.root / directory, self.repository
        )

    def test_deterministic_bytes_and_exact_native_archive_contract(self):
        first = self.build("first")
        second = self.build("second")
        self.assertEqual(first, second)
        filename = first["artifact"]["filename"]
        self.assertEqual(filename, "synthetic-led-0.1.0.zip")
        archive_path = self.root / "first" / filename
        self.assertEqual(archive_path.read_bytes(), (self.root / "second" / filename).read_bytes())
        self.assertEqual(
            first["artifact"]["sha256"], hashlib.sha256(archive_path.read_bytes()).hexdigest()
        )
        self.assertEqual(first["version"], "0.1.0")
        self.assertEqual(first["provenance"]["revision"], self.revision)
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertEqual(len(archive.namelist()), 4)
            for entry in archive.infolist():
                self.assertTrue(entry.filename.startswith("custom_components/synthetic_led/"))
                self.assertEqual(entry.date_time, ZIP_TIMESTAMP)
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(entry.create_system, 3)
                self.assertEqual(entry.external_attr >> 16, stat.S_IFREG | 0o644)
                relative = entry.filename.removeprefix("custom_components/synthetic_led/")
                self.assertEqual(archive.read(entry), (self.source / relative).read_bytes())
        destination = self.root / "manager-stage"
        destination.mkdir()
        extract_artifact(archive_path.read_bytes(), destination, first)
        self.assertEqual(json.loads((destination / "manifest.json").read_text()), self.manifest)

    def test_dirty_untracked_ignored_and_deleted_worktree_bytes_do_not_enter_zip(self):
        first = self.build("first")
        (self.source / "manifest.json").write_text("corrupted working tree\n")
        (self.source / "__init__.py").unlink()
        (self.source / "device.local.json").write_text('{"private":"synthetic"}\n')
        (self.source / ".env").write_text("SYNTHETIC=untracked\n")
        (self.source / "__pycache__").mkdir()
        (self.source / "__pycache__/code.pyc").write_bytes(b"synthetic bytecode")
        second = self.build("second")
        self.assertEqual(first, second)
        self.assertEqual(
            (self.root / "first" / first["artifact"]["filename"]).read_bytes(),
            (self.root / "second" / second["artifact"]["filename"]).read_bytes(),
        )

    def test_refuses_existing_output_without_changing_it(self):
        result = self.build()
        artifact = self.root / "artifacts" / result["artifact"]["filename"]
        before = artifact.read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(artifact.read_bytes(), before)

    def test_old_revision_stays_exact_after_new_commit_and_version(self):
        first = self.build("first")
        self.manifest["version"] = "0.2.0"
        self.write_manifest()
        revision = self.commit()
        latest = self.build("latest", revision)
        self.assertEqual(latest["version"], "0.2.0")
        self.assertNotEqual(first["artifact"]["sha256"], latest["artifact"]["sha256"])
        self.assertEqual(first, self.build("old"))

    def test_replace_refs_cannot_substitute_another_commits_bytes(self):
        first = self.build("first")
        self.manifest["version"] = "0.2.0"
        self.write_manifest()
        newer = self.commit()
        self.git("replace", self.revision, newer)
        self.assertEqual(first, self.build("original"))

    def test_rejects_noncommit_revision_and_moving_names(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        for revision in ("HEAD", "main", "../main", self.revision[:12], "f" * 40, tree):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.build(revision=revision)
        self.assertFalse((self.root / "artifacts").exists())

    def test_bounds_members_individual_files_and_total_before_writing(self):
        for limit in ("MAX_FILES", "MAX_FILE_BYTES", "MAX_CONTENT_BYTES"):
            with self.subTest(limit=limit), patch(f"tooling.build_module.{limit}", 1):
                with self.assertRaises(ValueError):
                    self.build()
        self.assertFalse((self.root / "artifacts").exists())

    def test_rejects_unsafe_domain_and_identity(self):
        for domain in ("../synthetic_led", "/synthetic_led", "synthetic-led", "Synthetic_Led"):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                build_artifact(domain, self.revision, self.root / "bad", self.repository)
        for identity in ("../bad", "latest/extra", "synthetic_led"):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                build_artifact(
                    "synthetic_led", self.revision, self.root / "bad", self.repository, identity
                )
        self.assertFalse((self.root / "bad").exists())

    def test_rejects_committed_non_native_and_private_files(self):
        forbidden = (
            ".env",
            "device.local.json",
            "raw-capture.json",
            "original.xapk",
            "install.sh",
            "code.pyc",
            "__pycache__/code.py",
            "tests/test_light.py",
            "translations/en.local.json",
        )
        for index, name in enumerate(forbidden):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic rejected content\n")
            revision = self.commit()
            with (
                self.subTest(path=name),
                self.assertRaisesRegex(ValueError, "unexpected_module_file"),
            ):
                self.build(f"bad-{index}", revision)
            self.assertFalse((self.root / f"bad-{index}").exists())
            path.unlink()

    def test_rejects_committed_symlinks_and_executable_files(self):
        link = self.source / "linked.py"
        link.symlink_to("__init__.py")
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "module_source_not_regular"):
            self.build("symlink", revision)
        link.unlink()
        executable = self.source / "install.py"
        executable.write_text('"""This must not be an executable installer."""\n')
        os.chmod(executable, 0o755)
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "module_source_not_regular"):
            self.build("executable", revision)

    def test_rejects_manifest_identity_requirements_version_and_missing_flow(self):
        for key, value in (
            ("domain", "another_domain"),
            ("requirements", ["synthetic-package==1.0.0"]),
            ("version", "latest"),
            ("version", "01.0.0"),
            ("config_flow", False),
        ):
            previous = self.manifest[key]
            self.manifest[key] = value
            self.write_manifest()
            revision = self.commit()
            with (
                self.subTest(key=key, value=value),
                self.assertRaisesRegex(ValueError, "module_manifest_invalid"),
            ):
                self.build(revision=revision)
            self.manifest[key] = previous
        self.write_manifest()
        (self.source / "config_flow.py").unlink()
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "module_manifest_invalid"):
            self.build(revision=revision)
        self.assertFalse((self.root / "artifacts").exists())

    def test_rejects_ambiguous_or_invalid_native_manifest_json(self):
        manifest = json.dumps(self.manifest)
        malformed = (
            "invalid JSON",
            "[]",
            manifest[:-1] + ', "version": "0.2.0"}',
            manifest[:-1] + ', "synthetic_nonfinite": NaN}',
        )
        for content in malformed:
            (self.source / "manifest.json").write_text(content)
            revision = self.commit()
            with (
                self.subTest(content=content),
                self.assertRaisesRegex(ValueError, "module_manifest_invalid"),
            ):
                self.build(revision=revision)
        self.assertFalse((self.root / "artifacts").exists())


if __name__ == "__main__":
    unittest.main()

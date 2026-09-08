"""Deterministic public artifacts and Supervisor build-context contract tests."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from tooling.build_fixture import FIXTURE_ROOT, ROOT, VERSIONS, build_artifact, build_release
from tooling.sync_manager_bundle import sync_bundle


class FixturePackagingTests(unittest.TestCase):
    def test_unexpected_ignored_files_cannot_enter_release_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            shutil.copytree(FIXTURE_ROOT, source)
            (source / ".env").write_text("synthetic-untracked-file\n")
            with self.assertRaisesRegex(ValueError, "unexpected_fixture_file"):
                build_artifact("0.1.0", root / "rejected.zip", source)
            self.assertFalse((root / "rejected.zip").exists())

    def test_artifacts_are_deterministic_and_match_catalog_manifest_and_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = build_release(output / "first", "a" * 40)
            second = build_release(output / "second", "a" * 40)
            self.assertEqual(first, second)
            schema = json.loads((ROOT / "schemas/catalog-v1.schema.json").read_text())
            Draft202012Validator(schema).validate(first)
            for module in first["modules"]:
                version = module["version"]
                name = f"hahapent-test-{version}.zip"
                archive_path = output / "first" / name
                self.assertEqual(archive_path.read_bytes(), (output / "second" / name).read_bytes())
                self.assertEqual(
                    hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    module["artifact"]["sha256"],
                )
                with zipfile.ZipFile(archive_path) as archive:
                    names = archive.namelist()
                    self.assertEqual(names, sorted(names))
                    self.assertEqual(len(names), len(set(names)))
                    self.assertTrue(
                        all(name.startswith("custom_components/hahapent_test/") for name in names)
                    )
                    self.assertTrue(all(".." not in Path(name).parts for name in names))
                    self.assertTrue(
                        all(stat.S_ISREG(info.external_attr >> 16) for info in archive.infolist())
                    )
                    manifest = json.loads(
                        archive.read("custom_components/hahapent_test/manifest.json")
                    )
                    self.assertEqual(manifest["domain"], module["integration_domain"])
                    self.assertEqual(manifest["version"], version)
                    self.assertEqual(manifest["requirements"], [])
                    self.assertTrue(manifest["config_flow"])
                    code = archive.read("custom_components/hahapent_test/const.py").decode()
                    self.assertIn(f'INTEGRATION_VERSION = "{version}"', code)
                    self.assertNotIn("schema_version", manifest)

    def test_fixture_is_outside_normal_catalog_and_release_tag_does_not_change_bytes(self):
        normal = json.loads((ROOT / "hahapent.json").read_text())
        self.assertFalse(
            any(module["integration_domain"] == "hahapent_test" for module in normal["modules"])
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = build_release(root / "fixture", "b" * 40)
            final = build_release(root / "final", "b" * 40, "v0.1.1")
            for version in VERSIONS:
                name = f"hahapent-test-{version}.zip"
                self.assertEqual(
                    (root / "fixture" / name).read_bytes(), (root / "final" / name).read_bytes()
                )
            self.assertNotEqual(
                fixture["modules"][0]["artifact"]["url"], final["modules"][0]["artifact"]["url"]
            )

    def test_builder_rejects_unversioned_release_or_unknown_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            for tag in ("main", "latest", "../v0.1.0", "test-fixtures-v0"):
                with self.assertRaises(ValueError):
                    build_release(destination, "a" * 40, tag)
            with self.assertRaises(ValueError):
                build_release(destination, "moving-branch")
            with self.assertRaises(ValueError):
                build_artifact("9.9.9", destination / "invalid.zip")

    def test_fixture_code_has_no_external_io_or_device_platforms(self):
        allowed_imports = {"homeassistant", "voluptuous"}
        for source in FIXTURE_ROOT.glob("*.py"):
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(
                        all(alias.name.split(".")[0] in allowed_imports for alias in node.names)
                    )
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module.split(".")[0], allowed_imports)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"open", "exec", "eval", "__import__"})
        sensor = (FIXTURE_ROOT / "sensor.py").read_text()
        self.assertIn("_attr_should_poll = False", sensor)
        self.assertNotIn("device_info", sensor)


class ManagerBundleTests(unittest.TestCase):
    def test_manager_release_alignment_does_not_change_frozen_fixtures(self):
        tree = ast.parse((ROOT / "manager/hahapent/__init__.py").read_text())
        version = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
        )
        self.assertEqual(version, "0.1.2")
        self.assertIn(f'version: "{version}"\n', (ROOT / "manager/config.yaml").read_text())
        self.assertIn(f"ARG BUILD_VERSION={version}\n", (ROOT / "manager/Dockerfile").read_text())
        frozen = json.loads((ROOT / "manager/test-catalog.json").read_text())
        self.assertEqual(frozen["minimum_manager_version"], "0.1.0")
        self.assertEqual({module["version"] for module in frozen["modules"]}, {"0.1.0", "0.2.0"})
        self.assertTrue(
            all(module["minimum_manager_version"] == "0.1.0" for module in frozen["modules"])
        )
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = build_release(Path(temporary), frozen["modules"][0]["provenance"]["revision"])
            self.assertEqual(rebuilt, frozen)

    def test_committed_runtime_bundle_matches_canonical_files(self):
        self.assertTrue(sync_bundle(check=True), "run tooling/sync_manager_bundle.py")

    def test_check_detects_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            (root / "hahapent.json").write_text("{}\n")
            (root / "schemas/catalog-v1.schema.json").write_text("{}\n")
            sync_bundle(root)
            destination = root / "manager/hahapent.json"
            destination.write_text('{"changed":true}\n')
            self.assertFalse(sync_bundle(root, check=True))
            self.assertEqual(destination.read_text(), '{"changed":true}\n')

    def test_packaging_has_exact_mount_and_no_lan_or_extra_api_permissions(self):
        text = (ROOT / "manager/config.yaml").read_text()
        self.assertIn("homeassistant_api: true", text)
        self.assertIn(
            "type: homeassistant_config\n    read_only: false\n    path: /homeassistant", text
        )
        self.assertIn("panel_admin: true", text)
        shutdown_window = int(
            next(
                line.partition(":")[2] for line in text.splitlines() if line.startswith("timeout:")
            )
        )
        self.assertGreaterEqual(shutdown_window, 30)
        for forbidden in ("ports:", "host_network:", "hassio_api:", "full_access:", "privileged:"):
            self.assertNotIn(forbidden, text)
        self.assertIn("  - amd64\n", text)
        self.assertNotIn("aarch64", text)
        dockerfile = (ROOT / "manager/Dockerfile").read_text()
        self.assertRegex(dockerfile, r"FROM python:3\.13\.[0-9]+-slim-bookworm@sha256:[0-9a-f]{64}")
        self.assertIn("--require-hashes", dockerfile)
        self.assertIn("--only-binary=:all:", dockerfile)
        self.assertIn("COPY schemas/ /app/schemas/", dockerfile)


if __name__ == "__main__":
    unittest.main()

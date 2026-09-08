"""Synthetic lifecycle, ownership and transaction fault-injection checks."""

import copy
import errno
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manager"))
from hahapent.catalog import ManagerError, catalog_url, load_catalog  # noqa: E402
from hahapent.engine import Manager  # noqa: E402
from hahapent.storage import atomic_json  # noqa: E402

REPOSITORY = "https://github.com/example/synthetic"
SOURCE = "synthetic-source"
DOMAIN = "synthetic_helper"
MODULE = "synthetic-helper"


def artifact(version="1.2.3", domain=DOMAIN, extras=None, manifest_extra=None):
    output = io.BytesIO()
    manifest = {"domain": domain, "version": version, "name": "Synthetic", "requirements": []}
    manifest.update(manifest_extra or {})
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("custom_components/" + domain + "/manifest.json", json.dumps(manifest))
        archive.writestr(
            "custom_components/" + domain + "/__init__.py", "VERSION = " + repr(version)
        )
        for name, content in (extras or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def release_catalog(repository=REPOSITORY, source_id=SOURCE, versions=("1.2.3", "1.2.4")):
    template = load_catalog(ROOT / "tests/fixtures/catalog/valid-synthetic.json")
    catalog = {key: copy.deepcopy(value) for key, value in template.items() if key != "modules"}
    catalog["source"].update(id=source_id, repository_url=repository)
    catalog["modules"] = []
    blobs = {}
    for version in versions:
        module = copy.deepcopy(template["modules"][0])
        module.update(version=version, license={"status": "pending"})
        module["provenance"]["repository_url"] = repository
        module["artifact"]["url"] = (
            repository + "/releases/download/test-v1/helper-" + version + ".zip"
        )
        content = artifact(version)
        module["artifact"]["sha256"] = hashlib.sha256(content).hexdigest()
        blobs[module["artifact"]["url"]] = content
        catalog["modules"].append(module)
    return catalog, blobs


class FakeHA:
    def __init__(self):
        self.version = "2026.9.1"
        self.core = set()
        self.entries = {}
        self.loaded_versions = {}

    def core_version(self):
        return self.version

    def is_core_domain(self, domain):
        return domain in self.core

    def config_entries(self, domain):
        return self.entries.get(domain, [])

    def domain_status(self, domain):
        return {
            "configured": bool(self.entries.get(domain)),
            "loaded": domain in self.loaded_versions,
            "loaded_version": self.loaded_versions.get(domain),
        }


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.config = self.base / "config"
        self.config.mkdir()
        self.data = self.base / "data"
        self.catalog, self.blobs = release_catalog()
        self.ha = FakeHA()
        self.requests = []
        self.manager = self.make_manager()

    def tearDown(self):
        self.temporary.cleanup()

    def download(self, url, max_bytes):
        self.requests.append((url, max_bytes))
        if url not in self.blobs:
            raise OSError("DO-NOT-ECHO")
        return self.blobs[url]

    def make_manager(self, **kwargs):
        return Manager(
            self.data,
            self.config,
            self.ha,
            self.download,
            builtin_catalog=kwargs.pop("builtin_catalog", self.catalog),
            **kwargs,
        )

    def install(self, version="1.2.3"):
        return self.manager.install(SOURCE, MODULE, version)

    def code_version(self):
        return json.loads(
            (self.config / "custom_components" / DOMAIN / "manifest.json").read_text()
        )["version"]

    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(ManagerError) as result:
            function(*args, **kwargs)
        self.assertEqual(result.exception.code, code)
        self.assertNotIn("DO-NOT-ECHO", str(result.exception))

    def test_complete_lifecycle_and_persistence(self):
        status = self.install()
        row = status["installed"][0]
        self.assertTrue(row["files_installed"])
        self.assertTrue(row["restart_pending"])
        self.assertFalse(row["configured"])
        self.assertEqual(self.code_version(), "1.2.3")
        self.ha.entries[DOMAIN] = [{"domain": DOMAIN, "state": "loaded"}]
        self.ha.loaded_versions[DOMAIN] = "1.2.3"
        self.assertFalse(self.manager.status()["installed"][0]["restart_pending"])
        self.install("1.2.4")
        self.assertEqual(self.code_version(), "1.2.4")
        self.assertTrue(self.manager.status()["installed"][0]["restart_pending"])
        self.manager = self.make_manager()
        self.assertEqual(self.manager.status()["installed"][0]["version"], "1.2.4")
        self.manager.rollback(DOMAIN)
        self.assertEqual(self.code_version(), "1.2.3")
        self.assert_error("removal_confirmation_required", self.manager.remove, DOMAIN)
        self.assert_error(
            "remove_native_config_entries_first", self.manager.remove, DOMAIN, confirmed=True
        )
        self.ha.entries.clear()
        status = self.manager.remove(DOMAIN, confirmed=True)
        self.assertEqual(status["installed"], [])
        self.assertFalse((self.config / "custom_components" / DOMAIN).exists())
        self.assertEqual(status["recovery"]["removed"][0]["version"], "1.2.3")
        self.manager = self.make_manager()
        self.assertTrue(self.manager.status()["recovery"]["removed"][0]["restart_pending"])
        self.assertTrue(self.manager.registry["removed"][DOMAIN]["restart_pending"])
        self.manager.rollback(DOMAIN)
        self.assertEqual(self.code_version(), "1.2.3")
        self.assertFalse(self.manager.journal_path.exists())

    def test_native_config_entry_created_during_backup_blocks_final_removal(self):
        self.install()
        with patch.object(self.ha, "config_entries", side_effect=[[], [{"domain": DOMAIN}]]):
            self.assert_error(
                "remove_native_config_entries_first", self.manager.remove, DOMAIN, confirmed=True
            )
        self.assertEqual(self.code_version(), "1.2.3")
        self.assertIn(DOMAIN, self.manager.registry["installed"])
        self.assertEqual(self.manager.registry["removed"], {})
        self.assertFalse(self.manager.journal_path.exists())

    def test_unrelated_configuration_is_unchanged(self):
        config = self.config / "configuration.yaml"
        config.write_text("synthetic: retained\n")
        sibling = self.config / "custom_components" / "unrelated"
        sibling.mkdir(parents=True)
        (sibling / "__init__.py").write_text("# retained")
        self.install()
        self.install("1.2.4")
        self.manager.remove(DOMAIN, confirmed=True)
        self.assertEqual(config.read_text(), "synthetic: retained\n")
        self.assertEqual((sibling / "__init__.py").read_text(), "# retained")

    def test_manual_or_hacs_directory_never_adopted(self):
        target = self.config / "custom_components" / DOMAIN
        target.mkdir(parents=True)
        (target / "manifest.json").write_text("manual")
        self.assert_error("ownership_conflict", self.install)
        self.assertEqual((target / "manifest.json").read_text(), "manual")
        self.assertEqual(self.requests, [])

    def test_core_owned_domain_is_blocked(self):
        self.ha.core.add(DOMAIN)
        self.assert_error("core_ownership_conflict", self.install)
        self.assertEqual(self.requests, [])

    def test_ownership_verifies_added_modified_missing_files_and_links(self):
        self.install()
        target = self.config / "custom_components" / DOMAIN
        for mode in ("extra", "modified", "missing", "link"):
            with self.subTest(mode=mode):
                source = target / "__init__.py"
                original = source.read_bytes()
                extra = target / "extra.py"
                if mode == "extra":
                    extra.write_text("unexpected")
                elif mode == "modified":
                    source.write_text("changed")
                elif mode == "missing":
                    source.unlink()
                else:
                    extra.symlink_to(self.config / "outside")
                self.assert_error("ownership_conflict", self.install, "1.2.4")
                if extra.exists() or extra.is_symlink():
                    extra.unlink()
                source.write_bytes(original)
        self.assertEqual(self.code_version(), "1.2.3")

    def test_symlink_target_parent_and_backup_are_rejected(self):
        other = self.base / "other"
        other.mkdir()
        components = self.config / "custom_components"
        components.symlink_to(other, target_is_directory=True)
        self.assert_error("unsafe_filesystem_path", self.install)
        components.unlink()
        self.install()
        self.install("1.2.4")
        previous = self.manager.registry["installed"][DOMAIN]["previous"]
        backup = self.manager.backups / previous["backup_id"]
        (backup / "evil.py").symlink_to(other / "file")
        self.assert_error("ownership_conflict", self.manager.rollback, DOMAIN)

    def test_exact_dependency_and_reverse_dependency_checks(self):
        helper = self.catalog["modules"][0]
        consumer = copy.deepcopy(helper)
        consumer.update(id="consumer", integration_domain="synthetic_consumer", version="2.0.0")
        consumer["dependencies"] = [{"source_id": SOURCE, "module_id": MODULE, "version": "1.2.3"}]
        consumer["artifact"]["url"] = REPOSITORY + "/releases/download/test-v1/consumer-2.0.0.zip"
        blob = artifact("2.0.0", "synthetic_consumer")
        consumer["artifact"]["sha256"] = hashlib.sha256(blob).hexdigest()
        self.catalog["modules"].append(consumer)
        self.blobs[consumer["artifact"]["url"]] = blob
        self.manager = self.make_manager()
        self.assert_error("dependency_unmet", self.manager.install, SOURCE, "consumer", "2.0.0")
        self.install()
        self.manager.install(SOURCE, "consumer", "2.0.0")
        self.assert_error("installed_dependent_conflict", self.install, "1.2.4")
        self.assert_error(
            "installed_dependent_conflict", self.manager.remove, DOMAIN, confirmed=True
        )
        self.manager.remove("synthetic_consumer", confirmed=True)
        self.install("1.2.4")

    def test_ha_unavailable_and_incompatible_fail_closed(self):
        with patch.object(self.ha, "core_version", side_effect=OSError("DO-NOT-ECHO")):
            self.assert_error("ha_status_unavailable", self.install)
            status = self.manager.status()
            self.assertIsNone(status["core_version"])
            self.assertTrue(all(not module["compatible"] for module in status["modules"]))
        self.ha.version = "2025.1.0"
        self.assert_error("ha_version_incompatible", self.install)
        self.ha.version = "2026.9.1"
        self.install()
        with patch.object(self.ha, "config_entries", return_value=None):
            self.assert_error("ha_status_unavailable", self.manager.remove, DOMAIN, confirmed=True)

    def test_download_failure_and_digest_failure_leave_no_install(self):
        first = self.catalog["modules"][0]["artifact"]["url"]
        del self.blobs[first]
        self.assert_error("download_failed", self.install)
        self.blobs[first] = b"corrupt"
        self.assert_error("artifact_digest_mismatch", self.install)
        self.assertEqual(self.manager.registry["installed"], {})
        self.assertFalse(self.manager.journal_path.exists())

    def test_undeclared_native_dependency_does_not_install(self):
        content = artifact(manifest_extra={"dependencies": ["untrusted_custom"]})
        module = self.catalog["modules"][0]
        self.blobs[module["artifact"]["url"]] = content
        module["artifact"]["sha256"] = hashlib.sha256(content).hexdigest()
        self.manager = self.make_manager()
        self.assert_error("undeclared_native_dependency", self.install)
        self.assertEqual(self.manager.registry["installed"], {})

    def test_explicit_source_trust_binding_and_offline_installed_retention(self):
        builtin = copy.deepcopy(self.catalog)
        builtin["modules"] = []
        builtin["source"].update(id="builtin", repository_url="https://github.com/example/builtin")
        self.blobs[catalog_url(REPOSITORY)] = json.dumps(self.catalog).encode()
        self.manager = self.make_manager(builtin_catalog=builtin)
        self.assert_error("source_trust_required", self.manager.add_source, REPOSITORY)
        self.assertEqual(self.requests, [])
        self.manager.add_source(REPOSITORY, trusted=True)
        self.assertEqual(self.manager.registry["installed"], {})
        self.install()
        del self.blobs[catalog_url(REPOSITORY)]
        status = self.manager.refresh_catalogs()
        self.assertEqual(status["installed"][0]["version"], "1.2.3")
        self.assertFalse(status["installed"][0]["source_available"])
        self.assert_error("source_unavailable", self.install, "1.2.4")
        self.manager.remove_source(SOURCE)
        self.assertEqual(self.code_version(), "1.2.3")
        other = "https://github.com/example/another"
        catalog, _ = release_catalog(other)
        self.blobs[catalog_url(other)] = json.dumps(catalog).encode()
        self.assert_error("source_identity_conflict", self.manager.add_source, other, trusted=True)
        self.manager.remove(DOMAIN, confirmed=True)
        self.assert_error("source_identity_conflict", self.manager.add_source, other, trusted=True)

    def test_test_catalog_is_explicit_and_never_changes_installed_files(self):
        empty = copy.deepcopy(self.catalog)
        empty["modules"] = []
        empty["source"]["id"] = "builtin"
        self.manager = self.make_manager(builtin_catalog=empty, test_catalog=self.catalog)
        self.assertEqual(self.manager.status()["modules"], [])
        self.manager.set_test_mode(True)
        self.install()
        self.manager.set_test_mode(False)
        self.assertEqual(self.manager.status()["modules"], [])
        self.assertEqual(self.code_version(), "1.2.3")

    def test_thread_and_process_lock_prevents_concurrent_mutations(self):
        with self.manager._serialized():
            self.assert_error("operation_in_progress", self.install)
            self.assert_error("operation_in_progress", self.make_manager)

    def test_interrupted_swap_rolls_back_after_each_precommit_phase(self):
        self.install()
        for phase in ("prepared", "staged", "old_moved", "new_moved"):
            with self.subTest(phase=phase):
                original = self.manager._journal

                def interrupt(transaction, next_phase):
                    original(transaction, next_phase)
                    if next_phase == phase:
                        raise SystemExit("synthetic power loss")

                with patch.object(self.manager, "_journal", side_effect=interrupt):
                    with self.assertRaises(SystemExit):
                        self.install("1.2.4")
                self.manager = self.make_manager()
                self.assertEqual(self.code_version(), "1.2.3")
                self.assertEqual(
                    self.manager.registry["installed"][DOMAIN]["module"]["version"], "1.2.3"
                )
                self.assertEqual(self.manager.recovery["result"], "rolled_back")
                self.assertFalse(self.manager.journal_path.exists())

    def test_interruption_after_registry_commit_finishes_commit(self):
        self.install()
        with patch.object(self.manager, "_finish", side_effect=SystemExit("synthetic power loss")):
            with self.assertRaises(SystemExit):
                self.install("1.2.4")
        self.manager = self.make_manager()
        self.assertEqual(self.code_version(), "1.2.4")
        self.assertEqual(self.manager.recovery["result"], "committed")
        self.manager.rollback(DOMAIN)
        self.assertEqual(self.code_version(), "1.2.3")

    def test_interrupted_install_and_remove_restore_correct_presence(self):
        for action in ("install", "remove"):
            original = self.manager._journal

            def interrupt(transaction, next_phase):
                original(transaction, next_phase)
                if next_phase == "new_moved":
                    raise SystemExit("synthetic power loss")

            with patch.object(self.manager, "_journal", side_effect=interrupt):
                with self.assertRaises(SystemExit):
                    if action == "install":
                        self.install()
                    else:
                        self.manager.remove(DOMAIN, confirmed=True)
            self.manager = self.make_manager()
            if action == "install":
                self.assertFalse((self.manager.components / DOMAIN).exists())
                self.install()
            else:
                self.assertEqual(self.code_version(), "1.2.3")

    def test_disk_full_before_registry_commit_restores_old_without_json_write(self):
        self.install()
        original = atomic_json

        def disk_full(path, value):
            if Path(path).name == "registry.json":
                raise OSError(errno.ENOSPC, "DO-NOT-ECHO")
            original(path, value)

        old_registry = self.manager.registry_path.read_bytes()
        with patch("hahapent.engine.atomic_json", side_effect=disk_full):
            self.assert_error("storage_failure", self.install, "1.2.4")
        self.assertEqual(self.code_version(), "1.2.3")
        self.assertEqual(self.manager.registry_path.read_bytes(), old_registry)
        self.assertFalse(self.manager.journal_path.exists())

    def test_disk_full_in_staging_and_before_journal_cannot_replace_live(self):
        self.install()
        with patch("hahapent.engine.extract_artifact", side_effect=OSError(errno.ENOSPC, "full")):
            self.assert_error("storage_failure", self.install, "1.2.4")
        self.assertEqual(self.code_version(), "1.2.3")
        with patch("hahapent.engine.atomic_json", side_effect=OSError(errno.ENOSPC, "full")):
            self.assert_error("storage_failure", self.install, "1.2.4")
        self.assertEqual(self.code_version(), "1.2.3")

    def test_recovery_refuses_externally_changed_target(self):
        self.install()
        original = self.manager._journal

        def interrupt(transaction, phase):
            original(transaction, phase)
            if phase == "new_moved":
                raise SystemExit()

        with patch.object(self.manager, "_journal", side_effect=interrupt):
            with self.assertRaises(SystemExit):
                self.install("1.2.4")
        (self.manager.components / DOMAIN / "extra.py").write_text("manual-change")
        self.assert_error("ownership_conflict", self.make_manager)
        self.assertTrue(self.manager.journal_path.exists())

    def test_bytecode_cache_is_allowed_but_cache_symlinks_are_not(self):
        self.install()
        cache = self.manager.components / DOMAIN / "__pycache__"
        cache.mkdir()
        (cache / "__init__.cpython-313.pyc").write_bytes(b"synthetic-cache")
        self.install("1.2.4")
        self.assertFalse(cache.exists())
        cache.mkdir()
        (cache / "__init__.cpython-313.pyc").symlink_to(self.config / "configuration.yaml")
        self.assert_error("ownership_conflict", self.manager.remove, DOMAIN, confirmed=True)

    def test_unrecognized_bytecode_and_nested_cache_directory_block_ownership(self):
        self.install()
        cache = self.manager.components / DOMAIN / "__pycache__"
        cache.mkdir()
        extra = cache / "unowned.cpython-313.pyc"
        extra.write_bytes(b"not-associated-with-owned-source")
        self.assert_error("ownership_conflict", self.manager.remove, DOMAIN, confirmed=True)
        extra.unlink()
        (cache / "nested").mkdir()
        self.assert_error("ownership_conflict", self.manager.remove, DOMAIN, confirmed=True)

    def test_manager_off_has_no_runtime_callback_requirement(self):
        self.install()
        code = self.manager.components / DOMAIN / "__init__.py"
        self.manager = None
        namespace = {}
        exec(compile(code.read_text(), "synthetic", "exec"), namespace)
        self.assertEqual(namespace["VERSION"], "1.2.3")


if __name__ == "__main__":
    unittest.main()

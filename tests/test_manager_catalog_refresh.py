"""Synthetic built-in catalog discovery, persistence and conservative fallback."""

import copy
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_manager_engine import (
    DOMAIN,
    MODULE,
    REPOSITORY,
    SOURCE,
    FakeHA,
    Manager,
    ManagerError,
    artifact,
    catalog_url,
    release_catalog,
)


class BuiltinCatalogRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.config = self.root / "config"
        self.config.mkdir()
        self.bundled, self.responses = release_catalog(versions=("1.2.3",))
        self.published = copy.deepcopy(self.bundled)
        added = copy.deepcopy(self.published["modules"][0])
        added.update(id="synthetic-second", integration_domain="synthetic_second", version="2.0.0")
        content = artifact(version="2.0.0", domain="synthetic_second")
        added["artifact"] = {
            "url": REPOSITORY + "/releases/download/module-v2/second-2.0.0.zip",
            "sha256": hashlib.sha256(content).hexdigest(),
            "format": "zip",
        }
        self.published["modules"].append(added)
        self.responses[added["artifact"]["url"]] = content
        self.responses[catalog_url(REPOSITORY)] = json.dumps(self.published).encode()
        self.requests = []
        self.manager = self.make_manager()

    def download(self, url, max_bytes):
        self.requests.append((url, max_bytes))
        value = self.responses.get(url, OSError("SYNTHETIC-DO-NOT-ECHO"))
        if isinstance(value, Exception):
            raise value
        return value

    def make_manager(self):
        return Manager(
            self.root / "data",
            self.config,
            FakeHA(),
            self.download,
            builtin_catalog=self.bundled,
        )

    def source(self):
        return next(source for source in self.manager.status()["sources"] if source["id"] == SOURCE)

    def test_startup_bootstraps_without_network_and_refresh_discovers_new_module_only(self):
        self.assertEqual(self.requests, [])
        self.assertEqual(self.source()["catalog_origin"], "bundled")
        self.assertEqual(self.source()["refresh_status"], "not_checked")
        self.assertEqual(len(self.manager.status()["modules"]), 1)
        self.manager.refresh_catalogs()
        self.assertEqual(len(self.manager.status()["modules"]), 2)
        self.assertEqual(self.requests, [(catalog_url(REPOSITORY), 2 * 1024 * 1024)])
        self.assertEqual(self.source()["catalog_origin"], "remote")
        self.assertEqual(self.source()["refresh_status"], "success")
        self.assertTrue(self.source()["last_successful_refresh"])
        self.assertEqual(self.manager.registry["installed"], {})
        self.assertEqual(list(self.config.iterdir()), [])
        self.assertFalse(self.manager.settings_path.exists())
        self.assertFalse(self.manager.registry_path.exists())

    def test_cached_catalog_revalidates_and_survives_restart_without_network(self):
        self.manager.refresh_catalogs()
        timestamp = self.source()["last_successful_refresh"]
        cache = self.manager.builtin_cache_path
        self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o600)
        self.requests.clear()
        self.responses[catalog_url(REPOSITORY)] = OSError("SYNTHETIC-OFFLINE")
        self.manager = self.make_manager()
        self.assertEqual(self.requests, [])
        self.assertEqual(len(self.manager.status()["modules"]), 2)
        self.assertEqual(self.source()["catalog_origin"], "cache")
        self.assertEqual(self.source()["refresh_status"], "not_checked")
        self.assertEqual(self.source()["last_successful_refresh"], timestamp)
        before = cache.read_bytes()
        self.manager.refresh_catalogs()
        self.assertEqual(cache.read_bytes(), before)
        self.assertEqual(self.source()["error"], "download_failed")
        self.assertEqual(self.source()["refresh_status"], "failed")
        self.assertEqual(self.source()["last_successful_refresh"], timestamp)
        self.assertTrue(self.source()["available"])
        self.assertNotIn("SYNTHETIC-OFFLINE", json.dumps(self.manager.status()))

    def test_first_failed_refresh_retains_bundled_catalog_and_reports_error(self):
        self.responses[catalog_url(REPOSITORY)] = OSError("SYNTHETIC-OFFLINE")
        self.manager.refresh_catalogs()
        self.assertEqual(len(self.manager.status()["modules"]), 1)
        self.assertEqual(self.source()["catalog_origin"], "bundled")
        self.assertEqual(self.source()["error"], "download_failed")
        self.assertFalse(self.manager.builtin_cache_path.exists())

    def test_rejected_remote_metadata_never_replaces_good_cache_or_catalog(self):
        self.manager.refresh_catalogs()
        before = self.manager.builtin_cache_path.read_bytes()
        invalid = []
        for key, value in (
            ("schema_version", 2),
            ("minimum_manager_version", "99.0.0"),
            ("required_features", ["unknown-feature"]),
        ):
            catalog = copy.deepcopy(self.published)
            catalog[key] = value
            invalid.append(json.dumps(catalog).encode())
        for key, value in (
            ("id", "different-source"),
            ("repository_url", "https://github.com/example/different"),
        ):
            catalog = copy.deepcopy(self.published)
            catalog["source"][key] = value
            invalid.append(json.dumps(catalog).encode())
        catalog = copy.deepcopy(self.published)
        catalog["modules"][0]["artifact"]["url"] = (
            "https://github.com/example/different/releases/download/v1/module-1.2.3.zip"
        )
        invalid.extend((json.dumps(catalog).encode(), b"invalid JSON", b'{"schema_version":1}'))
        for response in invalid:
            with self.subTest(response=response):
                self.responses[catalog_url(REPOSITORY)] = response
                self.manager.refresh_catalogs()
                self.assertEqual(self.manager.builtin_cache_path.read_bytes(), before)
                self.assertEqual(self.manager.catalogs[SOURCE], self.published)
                self.assertEqual(self.source()["refresh_status"], "failed")
                self.assertIn("error", self.source())

    def test_success_after_failed_refresh_clears_error_and_keeps_settings_and_owned_code(self):
        self.manager.install(SOURCE, MODULE, "1.2.3")
        registry = self.manager.registry_path.read_bytes()
        component = self.config / "custom_components" / DOMAIN / "__init__.py"
        original = component.read_bytes()
        self.responses[catalog_url(REPOSITORY)] = b"invalid"
        self.manager.refresh_catalogs()
        self.assertIn("error", self.source())
        self.responses[catalog_url(REPOSITORY)] = json.dumps(self.published).encode()
        self.manager.refresh_catalogs()
        self.assertNotIn("error", self.source())
        self.assertEqual(self.source()["refresh_status"], "success")
        self.assertEqual(self.manager.registry_path.read_bytes(), registry)
        self.assertEqual(component.read_bytes(), original)
        self.assertEqual(self.manager.registry["installed"][DOMAIN]["module"]["version"], "1.2.3")

    def test_extra_source_refresh_and_duplicate_source_guard_are_unchanged(self):
        other_repo = "https://github.com/example/extra"
        extra, _ = release_catalog(repository=other_repo, source_id="extra-source")
        self.responses[catalog_url(other_repo)] = json.dumps(extra).encode()
        self.manager.add_source(other_repo, trusted=True)
        settings = self.manager.settings_path.read_bytes()
        self.manager.refresh_catalogs()
        self.assertIn("extra-source", self.manager.catalogs)
        self.assertEqual(self.manager.settings_path.read_bytes(), settings)
        with self.assertRaisesRegex(ManagerError, "source_identity_conflict"):
            self.manager.add_source(REPOSITORY, trusted=True)
        self.responses[catalog_url(other_repo)] = OSError("SYNTHETIC-OFFLINE")
        self.manager.refresh_catalogs()
        self.assertNotIn("extra-source", self.manager.catalogs)
        self.assertEqual(self.source()["refresh_status"], "success")
        self.assertEqual(self.manager.settings_path.read_bytes(), settings)

    def test_corrupt_future_and_rebound_cache_is_preserved_and_never_used(self):
        self.manager.refresh_catalogs()
        original = json.loads(self.manager.builtin_cache_path.read_bytes())
        documents = [b"bad JSON"]
        for key, value in (
            ("schema_version", 2),
            ("schema_version", True),
            ("fetched_at", "not a timestamp"),
            ("fetched_at", "2026-01-01"),
        ):
            modified = copy.deepcopy(original)
            modified[key] = value
            documents.append(json.dumps(modified).encode())
        modified = copy.deepcopy(original)
        modified["catalog"]["source"]["id"] = "rebound-source"
        documents.append(json.dumps(modified).encode())
        for content in documents:
            with self.subTest(content=content):
                self.manager.builtin_cache_path.write_bytes(content)
                self.manager = self.make_manager()
                self.assertEqual(self.manager.catalogs[SOURCE], self.bundled)
                self.assertEqual(self.source()["cache_error"], "invalid_catalog_cache")
                self.manager.refresh_catalogs()
                self.assertEqual(self.manager.builtin_cache_path.read_bytes(), content)
                self.assertEqual(self.manager.catalogs[SOURCE], self.bundled)

    def test_cache_symlink_is_not_read_or_overwritten(self):
        target = self.root / "unrelated.json"
        target.write_text("synthetic unrelated file")
        self.manager.builtin_cache_path.symlink_to(target)
        self.manager = self.make_manager()
        self.manager.refresh_catalogs()
        self.assertEqual(self.source()["cache_error"], "invalid_catalog_cache")
        self.assertTrue(self.manager.builtin_cache_path.is_symlink())
        self.assertEqual(target.read_text(), "synthetic unrelated file")

    def test_disk_failure_during_refresh_preserves_good_catalog_and_cache(self):
        self.manager.refresh_catalogs()
        before = self.manager.builtin_cache_path.read_bytes()
        newer = copy.deepcopy(self.published)
        newer["source"]["name"] = "New synthetic name"
        self.responses[catalog_url(REPOSITORY)] = json.dumps(newer).encode()
        with patch("hahapent.engine.atomic_json", side_effect=OSError("SYNTHETIC-DISK-ERROR")):
            self.manager.refresh_catalogs()
        self.assertEqual(self.manager.builtin_cache_path.read_bytes(), before)
        self.assertEqual(self.manager.catalogs[SOURCE], self.published)
        self.assertEqual(self.source()["error"], "catalog_cache_write_failed")
        self.assertNotIn("SYNTHETIC-DISK-ERROR", json.dumps(self.manager.status()))

    def test_cache_envelope_structure_limit_never_invalidates_last_good_cache(self):
        self.manager.refresh_catalogs()
        before = self.manager.builtin_cache_path.read_bytes()
        candidate = copy.deepcopy(self.published)
        extension = 0
        for _ in range(62):
            extension = [extension]
        candidate["extensions"] = {"nested": extension}
        self.responses[catalog_url(REPOSITORY)] = json.dumps(candidate).encode()
        self.manager.refresh_catalogs()
        self.assertEqual(self.manager.builtin_cache_path.read_bytes(), before)
        self.assertEqual(self.source()["error"], "invalid_catalog")
        self.manager = self.make_manager()
        self.assertEqual(self.manager.catalogs[SOURCE], self.published)


if __name__ == "__main__":
    unittest.main()

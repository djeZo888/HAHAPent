"""V1 compatibility gates, persistent extensions and repository identities."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manager"))
from hahapent.catalog import (  # noqa: E402
    ManagerError,
    loads_json,
    repository_url,
    require_features,
    semver_key,
    validate_bound_catalog,
    validate_catalog,
    validate_document,
)
from hahapent.engine import DEFAULT_REGISTRY, DEFAULT_SETTINGS, Manager  # noqa: E402
from hahapent.storage import atomic_json  # noqa: E402

from tests.test_manager_engine import (  # noqa: E402
    DOMAIN,
    MODULE,
    REPOSITORY,
    SOURCE,
    FakeHA,
    release_catalog,
)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog, self.blobs = release_catalog()

    def test_original_empty_draft_is_read_without_invented_migration(self):
        old = {
            "schema_version": 1,
            "status": "draft",
            "source": self.catalog["source"],
            "modules": [],
        }
        before = copy.deepcopy(old)
        self.assertEqual(validate_catalog(old), [])
        validate_bound_catalog(old, REPOSITORY)
        self.assertEqual(old, before)
        old["modules"] = self.catalog["modules"]
        self.assertTrue(validate_catalog(old))

    def test_future_versions_of_each_document_rejected_without_rewrite(self):
        for kind, document in (("settings", DEFAULT_SETTINGS), ("registry", DEFAULT_REGISTRY)):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                config, data = root / "config", root / "data"
                config.mkdir()
                data.mkdir()
                path = data / (kind + ".json")
                value = copy.deepcopy(document)
                value["schema_version"] = 2
                original = json.dumps(value).encode()
                path.write_bytes(original)
                with self.assertRaisesRegex(ManagerError, "unsupported_schema_version"):
                    Manager(data, config, FakeHA(), builtin_catalog=self.catalog)
                self.assertEqual(path.read_bytes(), original)
        future = copy.deepcopy(self.catalog)
        future["schema_version"] = 2
        with self.assertRaisesRegex(ManagerError, "unsupported_schema_version"):
            validate_bound_catalog(future, REPOSITORY)

    def test_future_transaction_and_persistent_feature_gate_never_rewrite(self):
        for filename, value, code in (
            ("transaction.json", {"schema_version": 2}, "unsupported_schema_version"),
            (
                "settings.json",
                {**DEFAULT_SETTINGS, "required_features": ["future-critical"]},
                "unsupported_required_feature",
            ),
            (
                "registry.json",
                {**DEFAULT_REGISTRY, "minimum_manager_version": "9.0.0"},
                "manager_upgrade_required",
            ),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / "config").mkdir()
                (root / "data").mkdir()
                path = root / "data" / filename
                content = json.dumps(value)
                path.write_text(content)
                with self.assertRaisesRegex(ManagerError, code):
                    Manager(root / "data", root / "config", FakeHA(), builtin_catalog=self.catalog)
                self.assertEqual(path.read_text(), content)

    def test_duplicate_json_and_nonfinite_values_rejected_at_every_depth(self):
        for value in (
            '{"schema_version":1,"schema_version":2}',
            '{"extensions":{"a":1,"a":2}}',
            '{"extensions":{"x":NaN}}',
            '{"extensions":{"x":Infinity}}',
            '{"extensions":{"x":1e999}}',
            "[" * 70 + "0" + "]" * 70,
        ):
            with self.assertRaises(ValueError):
                loads_json(value)

    def test_released_module_description_docs_and_feature_gates_are_required(self):
        for key in (
            "description",
            "documentation_url",
            "minimum_manager_version",
            "required_features",
        ):
            catalog = copy.deepcopy(self.catalog)
            del catalog["modules"][0][key]
            self.assertTrue(validate_catalog(catalog))
        for key in ("minimum_manager_version", "required_features"):
            catalog = copy.deepcopy(self.catalog)
            del catalog[key]
            self.assertTrue(validate_catalog(catalog))

    def test_feature_and_semver_gate_fail_closed(self):
        self.assertLess(semver_key("0.1.0-rc.1"), semver_key("0.1.0"))
        self.assertLess(semver_key("0.1.0-alpha.2"), semver_key("0.1.0-alpha.10"))
        self.assertEqual(semver_key("0.1.0+one"), semver_key("0.1.0+two"))
        require_features({"minimum_manager_version": "0.1.0", "required_features": []})
        for value, error in (
            ({"minimum_manager_version": "0.2.0"}, "manager_upgrade_required"),
            ({"required_features": ["future-critical-behavior"]}, "unsupported_required_feature"),
        ):
            with self.assertRaisesRegex(ManagerError, error):
                require_features(value)

    def test_extensions_preserved_in_settings_catalog_and_registry_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config, data = root / "config", root / "data"
            config.mkdir()
            data.mkdir()
            settings = copy.deepcopy(DEFAULT_SETTINGS)
            settings["extensions"] = {"unknown.vendor": {"nested": ["retained", 42]}}
            registry = copy.deepcopy(DEFAULT_REGISTRY)
            registry["extensions"] = {"registry.future": {"color": "violet"}}
            atomic_json(data / "settings.json", settings)
            atomic_json(data / "registry.json", registry)
            self.catalog["extensions"] = {"catalog.future": {"opaque": True}}
            self.catalog["modules"][0]["extensions"] = {"module.future": ["retained"]}
            manager = Manager(
                data,
                config,
                FakeHA(),
                lambda url, max_bytes: self.blobs[url],
                builtin_catalog=self.catalog,
            )
            manager.set_test_mode(False)
            self.assertEqual(manager.settings["extensions"], settings["extensions"])
            manager.install(SOURCE, MODULE, "1.2.3")
            self.assertEqual(manager.registry["extensions"], registry["extensions"])
            entry = manager.registry["installed"][DOMAIN]
            self.assertEqual(entry["module"]["extensions"], {"module.future": ["retained"]})
            entry["extensions"] = {"installed.future": ["retained"]}
            atomic_json(manager.registry_path, manager.registry)
            manager.install(SOURCE, MODULE, "1.2.4")
            self.assertEqual(
                manager.registry["installed"][DOMAIN]["extensions"], entry["extensions"]
            )
            manager.rollback(DOMAIN)
            self.assertEqual(
                manager.registry["installed"][DOMAIN]["module"]["extensions"],
                {"module.future": ["retained"]},
            )
            self.assertEqual(manager.catalogs[SOURCE]["extensions"], self.catalog["extensions"])

    def test_optional_extensions_do_not_enable_unsupported_behavior(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["extensions"] = {"disable_tls": True, "skip_hash_check": True}
        catalog["modules"][0]["extensions"] = {"install_script": "DO-NOT-EXECUTE"}
        self.assertEqual(validate_catalog(catalog), [])
        validate_bound_catalog(catalog, REPOSITORY)
        self.assertNotIn("skip_hash_check", catalog["required_features"])

    def test_license_pending_has_no_invented_license_url(self):
        self.assertEqual(self.catalog["modules"][0]["license"], {"status": "pending"})
        self.assertEqual(validate_catalog(self.catalog), [])

    def test_multiple_pinned_versions_allowed_but_domain_takeover_rejected(self):
        self.assertEqual(validate_catalog(self.catalog), [])
        self.catalog["modules"][1]["integration_domain"] = "another_domain"
        self.assertIn("duplicate module identity", validate_catalog(self.catalog))

    def test_repository_normalization_and_bound_identity(self):
        self.assertEqual(repository_url(REPOSITORY + ".git/"), REPOSITORY)
        for value in (
            "http://github.com/example/synthetic",
            REPOSITORY + "?auth=DO-NOT-ECHO",
            "https://" + "user:DO-NOT-ECHO@github.com/example/synthetic",
            "https://github.com/example/../repo",
            "https://github.com/example/synthetic/tree/main",
            "https://localhost/example/synthetic",
        ):
            with self.assertRaisesRegex(ManagerError, "invalid_repository") as result:
                repository_url(value)
            self.assertNotIn("DO-NOT-ECHO", str(result.exception))
        with self.assertRaisesRegex(ManagerError, "source_repository_mismatch"):
            validate_bound_catalog(self.catalog, "https://github.com/example/different")
        with self.assertRaisesRegex(ManagerError, "source_identity_mismatch"):
            validate_bound_catalog(self.catalog, REPOSITORY, "different-id")

    def test_artifacts_and_provenance_bound_to_trusted_repository(self):
        for target in ("artifact", "provenance"):
            catalog = copy.deepcopy(self.catalog)
            if target == "artifact":
                catalog["modules"][0][target]["url"] = (
                    "https://github.com/example/other/releases/download/v1/helper-1.2.3.zip"
                )
            else:
                catalog["modules"][0][target]["repository_url"] = "https://github.com/example/other"
            with self.assertRaises(ManagerError):
                validate_bound_catalog(catalog, REPOSITORY)

    def test_moving_branch_or_latest_artifacts_rejected(self):
        for path in (
            "archive/refs/heads/main.zip",
            "releases/download/latest/helper-1.2.3.zip",
            "releases/download/main/helper-1.2.3.zip",
            "releases/download/v1/helper.zip",
        ):
            catalog = copy.deepcopy(self.catalog)
            catalog["modules"][0]["artifact"]["url"] = REPOSITORY + "/" + path
            with self.assertRaises(ManagerError):
                validate_bound_catalog(catalog, REPOSITORY)

    def test_bundled_schemas_never_follow_input_schema_url(self):
        self.catalog["$schema"] = "https://example.invalid/DO-NOT-FETCH"
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            validate_bound_catalog(self.catalog, REPOSITORY)
            validate_document(DEFAULT_SETTINGS, "settings")
            validate_document(DEFAULT_REGISTRY, "registry")

    def test_invalid_persistent_json_stays_byte_for_byte_unchanged(self):
        for text in (
            '{"schema_version":1,"schema_version":2}',
            '{"schema_version":1,"extensions":NaN}',
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / "config").mkdir()
                (root / "data").mkdir()
                path = root / "data" / "settings.json"
                path.write_text(text)
                with self.assertRaises(ManagerError):
                    Manager(root / "data", root / "config", FakeHA(), builtin_catalog=self.catalog)
                self.assertEqual(path.read_text(), text)


if __name__ == "__main__":
    unittest.main()

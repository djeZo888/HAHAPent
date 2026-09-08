"""Offline contract tests use public metadata, synthetic catalogs and temporary files."""

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tooling.validate_catalog import ROOT, load_catalog, main, validate_catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "tests/fixtures/catalog/valid-synthetic.json")

    def assert_invalid(self, catalog=None, contains=None):
        errors = validate_catalog(self.catalog if catalog is None else catalog)
        self.assertTrue(errors)
        if contains:
            self.assertTrue(any(contains in error for error in errors), errors)
        return errors

    def test_builtin_catalog_is_valid_and_excludes_device_free_fixture(self):
        catalog = load_catalog(ROOT / "hahapent.json")
        self.assertEqual(validate_catalog(catalog), [])
        self.assertTrue(all(m["integration_domain"] != "hahapent_test" for m in catalog["modules"]))

    def test_valid_synthetic_catalog(self):
        self.assertEqual(validate_catalog(self.catalog), [])

    def test_reject_unknown_schema_version(self):
        self.catalog["schema_version"] = 2
        self.assert_invalid(contains="const")

    def test_reject_additional_properties_at_each_object_level(self):
        paths = (
            (),
            ("source",),
            ("modules", 0),
            ("modules", 0, "home_assistant"),
            ("modules", 0, "artifact"),
            ("modules", 0, "license"),
            ("modules", 0, "provenance"),
            ("modules", 0, "restart"),
            ("modules", 1, "dependencies", 0),
        )
        for path in paths:
            with self.subTest(path=path):
                catalog = copy.deepcopy(self.catalog)
                target = catalog
                for part in path:
                    target = target[part]
                target["unexpected"] = "synthetic"
                self.assert_invalid(catalog, "additionalProperties")

    def test_reject_missing_required_module_metadata(self):
        for field in self.catalog["modules"][0]:
            with self.subTest(field=field):
                catalog = copy.deepcopy(self.catalog)
                del catalog["modules"][0][field]
                self.assert_invalid(catalog, "required")

    def test_reject_duplicate_ids(self):
        self.catalog["modules"][1]["id"] = self.catalog["modules"][0]["id"]
        self.assert_invalid(contains="duplicate module identity")

    def test_reject_duplicate_domains(self):
        self.catalog["modules"][1]["integration_domain"] = self.catalog["modules"][0][
            "integration_domain"
        ]
        self.assert_invalid(contains="duplicate integration domain")

    def test_reject_missing_local_dependency(self):
        self.catalog["modules"][1]["dependencies"][0]["module_id"] = "missing-module"
        self.assert_invalid(contains="absent from catalog")

    def test_reject_dependency_version_mismatch(self):
        self.catalog["modules"][1]["dependencies"][0]["version"] = "9.0.0"
        self.assert_invalid(contains="version mismatch")

    def test_reject_repeated_dependency_with_different_version(self):
        dependency = copy.deepcopy(self.catalog["modules"][1]["dependencies"][0])
        dependency["version"] = "9.0.0"
        self.catalog["modules"][1]["dependencies"].append(dependency)
        self.assert_invalid(contains="duplicate dependency identity")

    def test_reject_self_dependency(self):
        self.catalog["modules"][0]["dependencies"] = [
            {"source_id": "synthetic-source", "module_id": "synthetic-helper", "version": "1.2.3"}
        ]
        self.assert_invalid(contains="cannot depend on itself")

    def test_reject_dependency_cycle(self):
        self.catalog["modules"][0]["dependencies"] = [
            {
                "source_id": "synthetic-source",
                "module_id": "synthetic-consumer",
                "version": "2.0.0-rc.1",
            }
        ]
        self.assert_invalid(contains="dependency cycle")

    def test_external_dependency_is_metadata_only(self):
        self.catalog["modules"][1]["dependencies"][0]["source_id"] = "external-example"
        # No fetch, trust decision, availability claim, or installation occurs.
        with patch("socket.socket", side_effect=AssertionError("network is forbidden")):
            self.assertEqual(validate_catalog(self.catalog), [])

    def test_input_schema_reference_is_never_fetched(self):
        self.catalog["$schema"] = "https://example.invalid/must-not-fetch.json"
        with patch("socket.socket", side_effect=AssertionError("network is forbidden")):
            self.assertEqual(validate_catalog(self.catalog), [])

    def test_reject_bad_semver(self):
        for version in ("1.2", "01.2.3", "1.2.3-01", "latest"):
            with self.subTest(version=version):
                self.catalog["modules"][0]["version"] = version
                self.assert_invalid(contains="pattern")

    def test_reject_bad_home_assistant_version(self):
        self.catalog["modules"][0]["home_assistant"]["min_version"] = "2026.13.0"
        self.assert_invalid(contains="pattern")

    def test_reject_empty_or_reversed_compatibility_range(self):
        for maximum in ("2026.1.0", "2025.12.0"):
            with self.subTest(maximum=maximum):
                self.catalog["modules"][0]["home_assistant"]["max_version_exclusive"] = maximum
                self.assert_invalid(contains="maximum must be greater")

    def test_reject_invalid_digest(self):
        self.catalog["modules"][0]["artifact"]["sha256"] = "0" * 63
        self.assert_invalid(contains="pattern")

    def test_reject_trailing_newline_in_full_string_patterns(self):
        paths = (
            ("source", "id"),
            ("modules", 0, "id"),
            ("modules", 0, "integration_domain"),
            ("modules", 0, "version"),
            ("modules", 0, "home_assistant", "min_version"),
            ("modules", 0, "artifact", "sha256"),
            ("modules", 0, "provenance", "revision"),
            ("modules", 0, "provenance", "source_path"),
        )
        for path in paths:
            with self.subTest(path=path):
                catalog = copy.deepcopy(self.catalog)
                target = catalog
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] += "\n"
                self.assert_invalid(catalog, "pattern")

    def test_reject_unpinned_provenance(self):
        self.catalog["modules"][0]["provenance"]["revision"] = "main"
        self.assert_invalid(contains="pattern")

    def test_reject_unsafe_source_paths(self):
        for source_path in (
            "../module",
            "modules/../module",
            "./module",
            "/module",
            "modules\\module",
        ):
            with self.subTest(source_path=source_path):
                self.catalog["modules"][0]["provenance"]["source_path"] = source_path
                self.assert_invalid()

    def test_reject_unsafe_urls_without_echoing_values(self):
        urls = (
            "http://example.invalid/artifact.zip",
            "https://" + "synthetic-user:DO-NOT-ECHO" + "@example.invalid/artifact.zip",
            "https://example.invalid/artifact.zip?key=DO-NOT-ECHO",
            "https://example.invalid/artifact.zip#DO-NOT-ECHO",
            "https://example.invalid:99999/artifact.zip",
            "https:///artifact.zip",
            "https://example.invalid\\artifact.zip",
        )
        for url in urls:
            with self.subTest(url=url):
                self.catalog["modules"][0]["artifact"]["url"] = url
                errors = self.assert_invalid()
                self.assertNotIn("DO-NOT-ECHO", "\n".join(errors))

    def test_reject_ambiguous_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            for content in (
                '{"schema_version":1,"schema_version":2}',
                '{"value":NaN}',
                '{"value":Infinity}',
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_catalog(path)

    def test_cli_failure_is_nonzero_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text('{"secret":"DO-NOT-ECHO"}', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([str(path)])
            self.assertEqual(result, 1)
            self.assertIn("FAIL", output.getvalue())
            self.assertNotIn("DO-NOT-ECHO", output.getvalue())

    def test_cli_default_catalog(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertIn("offline only", output.getvalue())


if __name__ == "__main__":
    unittest.main()

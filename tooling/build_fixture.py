"""Build deterministic, device-free release artifacts; no network or Git writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "modules/hahapent_test/custom_components/hahapent_test"
REPOSITORY_URL = "https://github.com/djeZo888/HAHAPent"
MANAGER_VERSION = "0.1.0"
DEFAULT_RELEASE_TAG = "test-fixtures-v1"
VERSIONS = ("0.1.0", "0.2.0")
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
FIXTURE_FILES = frozenset(
    {
        "__init__.py",
        "config_flow.py",
        "const.py",
        "manifest.json",
        "sensor.py",
        "strings.json",
        "translations/en.json",
    }
)


def build_artifact(version: str, output: Path, source: Path = FIXTURE_ROOT) -> str:
    """Produce stable ZIP bytes regardless of source mtimes or host ZIP library."""
    if version not in VERSIONS:
        raise ValueError("unsupported_fixture_version")
    entries = list(source.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("fixture_source_invalid")
    files = sorted(
        path
        for path in entries
        if path.is_file()
        and "__pycache__" not in path.relative_to(source).parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    if {path.relative_to(source).as_posix() for path in files} != FIXTURE_FILES:
        raise ValueError("unexpected_fixture_file")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stored entries intentionally avoid zlib-version differences across builders.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            relative = path.relative_to(source)
            content = path.read_bytes()
            if relative.as_posix() == "manifest.json":
                manifest = json.loads(content)
                if manifest["domain"] != "hahapent_test" or manifest["version"] != VERSIONS[0]:
                    raise ValueError("fixture_manifest_invalid")
                manifest["version"] = version
                content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            elif relative.as_posix() == "const.py":
                original = f'INTEGRATION_VERSION = "{VERSIONS[0]}"'.encode()
                if content.count(original) != 1:
                    raise ValueError("fixture_version_invalid")
                content = content.replace(original, f'INTEGRATION_VERSION = "{version}"'.encode())
            info = zipfile.ZipInfo("custom_components/hahapent_test/" + relative.as_posix())
            info.date_time = ZIP_TIMESTAMP
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def build_release(
    output_dir: Path, revision: str, release_tag: str = DEFAULT_RELEASE_TAG
) -> dict[str, Any]:
    """Build A/B and a test catalog tied to an explicitly versioned release tag."""
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("source_revision_required")
    if re.fullmatch(r"(?:test-fixtures-v[1-9][0-9]*|v[0-9]+\.[0-9]+\.[0-9]+)", release_tag) is None:
        raise ValueError("versioned_release_tag_required")
    output_dir.mkdir(parents=True, exist_ok=True)
    modules = []
    for version in VERSIONS:
        filename = f"hahapent-test-{version}.zip"
        digest = build_artifact(version, output_dir / filename)
        modules.append(
            {
                "id": "hahapent-test",
                "name": "HAHAPent device-free test",
                "description": (
                    "Acceptance-test sensor reporting its loaded code version. "
                    "No devices or network actions."
                ),
                "documentation_url": REPOSITORY_URL
                + "/blob/"
                + revision
                + "/modules/hahapent_test/README.md",
                "integration_domain": "hahapent_test",
                "version": version,
                "minimum_manager_version": MANAGER_VERSION,
                "required_features": [],
                "home_assistant": {"min_version": "2026.9.1", "max_version_exclusive": "2026.9.2"},
                "dependencies": [],
                "artifact": {
                    "url": REPOSITORY_URL + f"/releases/download/{release_tag}/" + filename,
                    "sha256": digest,
                    "format": "zip",
                },
                "license": {"status": "pending"},
                "provenance": {
                    "repository_url": REPOSITORY_URL,
                    "revision": revision,
                    "source_path": "modules/hahapent_test",
                },
                "restart": {"home_assistant": "required", "manager": "not_required"},
                "extensions": {"test_fixture": True},
            }
        )
    catalog = {
        "schema_version": 1,
        "status": "released",
        "source": {
            "id": "hahapent-test",
            "name": "HAHAPent acceptance-test fixtures",
            "repository_url": REPOSITORY_URL,
        },
        "minimum_manager_version": MANAGER_VERSION,
        "required_features": [],
        "modules": modules,
        "extensions": {"test_fixture": True},
    }
    (output_dir / "test-catalog.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return catalog


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--revision", required=True, help="Published source commit, 40 lowercase hex"
    )
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG)
    arguments = parser.parse_args(argv)
    try:
        catalog = build_release(arguments.output_dir, arguments.revision, arguments.release_tag)
        print(json.dumps({"status": "PASS", "artifacts": len(catalog["modules"])}))
        return 0
    except Exception:
        print('{"status": "FAIL", "reason": "fixture_build_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

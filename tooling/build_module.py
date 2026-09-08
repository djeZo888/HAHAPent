"""Build a deterministic native integration ZIP from an exact committed Git tree.

This command never reads integration bytes from the working tree, invokes an
installer, writes Git state, or publishes a release. Review and secret-scan the
source commit before building; the publisher owns release and catalog metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
# Match the Manager's 2,000-member/8-MiB-file limits. Reserve 2 MiB of its
# 32-MiB archive limit for central-directory headers and bounded entry paths.
MAX_FILES = 2000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_CONTENT_BYTES = 30 * 1024 * 1024
DOMAIN_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}")
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def _git(repository: Path, *arguments: str) -> bytes:
    """Read public Git objects, without returning raw Git error output."""
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repository), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        raise ValueError("committed_source_unavailable") from None


def _native_path(name: str) -> bool:
    """Allow native Python and HA metadata, rejecting state and private inputs.

    Extend this explicit contract only when a later native integration needs a
    reviewed additional resource type. Arbitrary JSON/archives are not assets.
    """
    path = PurePosixPath(name)
    if len(name) > 200 or path.is_absolute() or name != path.as_posix():
        return False
    if any(
        re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) is None
        or part in {".", "..", "__pycache__", "tests", "captures", "backups"}
        or ".local." in part
        for part in path.parts
    ):
        return False
    if path.suffix == ".py":
        return True
    if name in {"manifest.json", "strings.json", "icons.json", "services.yaml"}:
        return True
    return len(path.parts) == 2 and path.parts[0] == "translations" and path.suffix == ".json"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("module_manifest_invalid")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Any:
    raise ValueError("module_manifest_invalid")


def committed_files(domain: str, revision: str, repository: Path = ROOT) -> dict[str, bytes]:
    """Return validated ordinary-file blobs, never untracked or modified bytes."""
    if DOMAIN_PATTERN.fullmatch(domain) is None:
        raise ValueError("integration_domain_invalid")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("source_revision_required")
    if _git(repository, "cat-file", "-t", revision).strip() != b"commit":
        raise ValueError("source_revision_not_commit")
    prefix = f"modules/{domain}/custom_components/{domain}/"
    tree = _git(repository, "ls-tree", "-r", "-z", revision, "--", prefix)
    entries = tree.split(b"\0")
    if not tree or len(entries) - 1 > MAX_FILES:
        raise ValueError("module_source_invalid")
    files: dict[str, bytes] = {}
    folded = set()
    aliases: dict[str, str] = {}
    total = 0
    for entry in entries:
        if not entry:
            continue
        try:
            header, raw_path = entry.split(b"\t", 1)
            mode, kind, object_id = header.split(b" ")
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            raise ValueError("module_source_invalid") from None
        if mode != b"100644" or kind != b"blob" or not path.startswith(prefix):
            raise ValueError("module_source_not_regular")
        relative = path[len(prefix) :]
        if not _native_path(relative) or relative.casefold() in folded:
            raise ValueError("unexpected_module_file")
        parts = relative.split("/")
        for count in range(1, len(parts) + 1):
            parent = "/".join(parts[:count])
            if aliases.get(parent.casefold(), parent) != parent:
                raise ValueError("unexpected_module_file")
            aliases[parent.casefold()] = parent
        folded.add(relative.casefold())
        size = int(_git(repository, "cat-file", "-s", object_id.decode("ascii")))
        total += size
        if size > MAX_FILE_BYTES or total > MAX_CONTENT_BYTES:
            raise ValueError("module_source_too_large")
        files[relative] = _git(repository, "cat-file", "blob", object_id.decode("ascii"))
    if not {"__init__.py", "manifest.json"}.issubset(files):
        raise ValueError("module_native_files_missing")
    return files


def build_artifact(
    domain: str,
    revision: str,
    output_dir: Path,
    repository: Path = ROOT,
    module_id: str | None = None,
) -> dict[str, Any]:
    """Build immutable source bytes and return neutral publication metadata."""
    identity = module_id if module_id is not None else domain.replace("_", "-")
    if ID_PATTERN.fullmatch(identity) is None:
        raise ValueError("module_id_invalid")
    files = committed_files(domain, revision, repository)
    try:
        manifest = json.loads(
            files["manifest.json"],
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError):
        raise ValueError("module_manifest_invalid") from None
    if (
        not isinstance(manifest, dict)
        or manifest.get("domain") != domain
        or not isinstance(manifest.get("version"), str)
        or VERSION_PATTERN.fullmatch(manifest["version"]) is None
        or manifest.get("requirements") != []
        or manifest.get("config_flow") is not True
        or "config_flow.py" not in files
    ):
        raise ValueError("module_manifest_invalid")
    version = manifest["version"]
    filename = f"{identity}-{version}.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / filename
    # Refuse overwrites: an existing release candidate must remain reviewable.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
        for relative, content in sorted(files.items()):
            info = zipfile.ZipInfo(f"custom_components/{domain}/{relative}")
            info.date_time = ZIP_TIMESTAMP
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)
    return {
        "id": identity,
        "integration_domain": domain,
        "version": version,
        "artifact": {
            "filename": filename,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "format": "zip",
        },
        "provenance": {"revision": revision, "source_path": f"modules/{domain}"},
        "files": len(files),
    }


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--module-id")
    parser.add_argument("--revision", required=True, help="Exact source commit, 40 lowercase hex")
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = build_artifact(
            arguments.domain,
            arguments.revision,
            arguments.output_dir,
            module_id=arguments.module_id,
        )
    except Exception:
        print('{"status":"FAIL","reason":"module_build_failed"}', file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

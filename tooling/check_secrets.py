"""Fail closed on forbidden Git paths, token patterns, and actual private values.

No matching text, secret-derived hashes, remote errors, or file contents are
printed. This is a publication guard, not a claim to detect every possible secret.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORBIDDEN_NAMES = (
    "credentials*.txt",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.knxproj",
    "*.knxkeys",
    "*.knxprojarchive",
    "*.pcap",
    "*.pcapng",
    "*.db",
    "*.db-*",
    "*.sqlite*",
    "*.log",
    "*.backup",
    "*.bak",
    "*.tar",
    "*.tar.gz",
    "bootstrap.json",
    "local-profile*.json",
    "id_rsa*",
    "id_ed25519*",
    "*handoff*.md",
    "*handoff*.txt",
    "HAHAPent_Task_*",
    "device.local.json",
    "*.xapk",
    "*.apk",
    "*.dex",
)
FORBIDDEN_DIRS = frozenset(
    {
        "secrets",
        "private",
        "private_evidence",
        "backups",
        "logs",
        ".storage",
        "recordings",
        "runtime-profiles",
        "handoffs",
        ".venv",
    }
)
PATTERNS = (
    ("github_token", re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("jwt_token", re.compile(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}")),
    (
        "private_key",
        re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    ),
    ("credential_url", re.compile(rb"https?://[^\s/@:]+:[^\s/@]+@")),
)


def inspect_blob(path: str, data: bytes, private_values: tuple[bytes, ...] = ()) -> list[str]:
    parts = Path(path).parts
    sanitized_example = path.endswith((".example", ".example.json"))
    findings = []
    if any(part in FORBIDDEN_DIRS or part.startswith("private-") for part in parts):
        findings.append("forbidden_path")
    if not sanitized_example and any(
        fnmatch.fnmatchcase(Path(path).name, p) for p in FORBIDDEN_NAMES
    ):
        findings.append("forbidden_path")
    # A filename can itself contain a token, household identifier, or password.
    encoded_path = path.encode("utf-8")
    findings.extend(
        name for name, pattern in PATTERNS if pattern.search(data) or pattern.search(encoded_path)
    )
    if any(value and (value in data or value in encoded_path) for value in private_values):
        findings.append("private_value")
    return sorted(set(findings))


def git(*args: str) -> bytes:
    # Replacement refs affect local presentation, not the bytes a push publishes.
    result = subprocess.run(
        ["git", "--no-replace-objects", *args], cwd=ROOT, capture_output=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError("git_check_failed")
    return result.stdout


def _tree_entries(revision: str) -> list[tuple[str, str]]:
    """Inspect every path, even when its blob also occurs under another name.

    NUL-delimited records preserve tabs and newlines in Git filenames. Including
    trees checks forbidden directory names even for an explicitly empty tree.
    Symlinks remain blob objects: their link text is scanned, never followed.
    """
    entries = []
    for record in git("ls-tree", "-r", "-t", "-z", "--full-tree", revision).split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        filemode, kind, oid = meta.split()
        if filemode == b"160000" or kind not in {b"blob", b"tree"}:
            raise RuntimeError("unsupported_tree_entry")
        entries.append((oid.decode("ascii"), path.decode("utf-8")))
    return entries


def objects(mode: str, upstream: str | None) -> list[tuple[str, str]]:
    if mode == "staged":
        entries = []
        for record in git("ls-files", "--stage", "-z").split(b"\0"):
            if not record:
                continue
            meta, path = record.split(b"\t", 1)
            filemode, oid, stage = meta.split()
            if stage != b"0" or filemode == b"160000":
                raise RuntimeError("unsupported_index_entry")
            entries.append((oid.decode("ascii"), path.decode("utf-8")))
        return entries
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise RuntimeError("incomplete_git_history")
    revisions = ["--all"]
    if mode == "outgoing":
        if not upstream or upstream.startswith("-"):
            raise RuntimeError("invalid_upstream")
        # Resolve before constructing a revision expression; reject nonexistent refs.
        base = git("rev-parse", "--verify", upstream + "^{commit}").decode().strip()
        revisions = [base + "..HEAD"]

    # rev-list --objects emits each object once, with at most one path. Its
    # outgoing range also excludes blobs already reachable from the base, even
    # if a new commit installs them at a forbidden path. Enumerate each target
    # commit's complete tree independently of the object reachability delta.
    entries = [
        (oid.decode("ascii"), "")
        for oid in git("rev-list", "--objects", "--no-object-names", *revisions).splitlines()
    ]
    for commit in git("rev-list", *revisions).splitlines():
        entries.extend(_tree_entries(commit.decode("ascii")))

    if mode == "history":
        # Explicit ref traversal also covers annotated/nested tags and refs
        # pointing directly to blobs or trees, which need not reach a commit.
        pending = list(git("for-each-ref", "--format=%(objectname)").splitlines())
        seen = set()
        while pending:
            oid = pending.pop().decode("ascii")
            if oid in seen:
                continue
            seen.add(oid)
            entries.append((oid, ""))
            kind = git("cat-file", "-t", oid).strip()
            if kind == b"tag":
                if int(git("cat-file", "-s", oid)) > 5 * 1024 * 1024:
                    raise RuntimeError("oversized_git_object")
                first_line = git("cat-file", "-p", oid).split(b"\n", 1)[0]
                label, separator, target = first_line.partition(b" ")
                if label != b"object" or not separator:
                    raise RuntimeError("invalid_tag_object")
                pending.append(target)
            elif kind == b"tree":
                entries.extend(_tree_entries(oid))

    return list(dict.fromkeys(entries))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--history", action="store_true")
    mode.add_argument("--outgoing", metavar="UPSTREAM")
    parser.add_argument(
        "--no-private-values",
        action="store_true",
        help="Synthetic CI only; skip local credential comparison",
    )
    args = parser.parse_args(argv)
    selected = "staged" if args.staged else "outgoing" if args.outgoing else "history"
    try:
        values: tuple[bytes, ...] = ()
        if not args.no_private_values:
            from tooling.access import load_private_profile, read_private_file

            c = load_private_profile().credentials
            values = tuple(
                v.encode()
                for v in (c.github_token, c.ha_token, c.ha_password, c.ha_host, c.ha_username)
            )
            device_path = Path.home() / ".config/hahapent/devices/aquarius_plant_led.json"
            if device_path.exists():
                device = json.loads(read_private_file(device_path))
                if device.get("integration_domain") != "aquarius_plant_led":
                    raise ValueError("private_device_profile_invalid")
                host = device.get("host")
                if not isinstance(host, str) or not host:
                    raise ValueError("private_device_profile_invalid")
                values += (host.encode(),)
        findings = []
        scanned = 0
        for oid, path in objects(selected, args.outgoing):
            kind = git("cat-file", "-t", oid).strip()
            if kind not in {b"blob", b"commit", b"tag", b"tree"}:
                raise RuntimeError("unsupported_git_object")
            data = b""
            if kind != b"tree":
                if int(git("cat-file", "-s", oid)) > 5 * 1024 * 1024:
                    raise RuntimeError("oversized_git_object")
                data = git("cat-file", "-p", oid)
            categories = inspect_blob(path, data, values)
            scanned += 1
            if categories:
                # Deliberately omit path because even filenames can contain secrets.
                findings.append({"object_number": scanned, "categories": categories})
        print(
            json.dumps(
                {
                    "status": "FAIL" if findings else "PASS",
                    "mode": selected,
                    "objects_scanned": scanned,
                    "private_value_comparison": not args.no_private_values,
                    "findings": findings,
                },
                sort_keys=True,
            )
        )
        return 1 if findings else 0
    except Exception:
        print(json.dumps({"status": "BLOCKED", "reason": "secret_check_incomplete"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

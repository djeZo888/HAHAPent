"""Copy canonical public schemas/catalog into the Supervisor App build context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def bundle_files(root: Path = ROOT) -> dict[Path, bytes]:
    sources = [root / "hahapent.json", *sorted((root / "schemas").glob("*.schema.json"))]
    return {root / "manager" / source.relative_to(root): source.read_bytes() for source in sources}


def sync_bundle(root: Path = ROOT, *, check: bool = False) -> bool:
    files = bundle_files(root)
    stale = any(
        not path.is_file() or path.read_bytes() != content for path, content in files.items()
    )
    expected_schemas = {path.name for path in files if path.parent.name == "schemas"}
    existing_schemas = {path.name for path in (root / "manager/schemas").glob("*.schema.json")}
    if existing_schemas - expected_schemas:
        # Never silently delete a bundle file; remove obsolete schemas explicitly.
        raise ValueError("unexpected_bundled_schema")
    if not check:
        for destination, content in files.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    return not stale


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on drift without writing")
    arguments = parser.parse_args(argv)
    try:
        current = sync_bundle(check=arguments.check)
        if arguments.check and not current:
            print("manager_bundle_drift", file=sys.stderr)
            return 1
        print("manager_bundle_current" if arguments.check else "manager_bundle_synchronized")
        return 0
    except Exception:
        print("manager_bundle_invalid", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

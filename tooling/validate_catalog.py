#!/usr/bin/env python3
"""Validate catalog metadata offline; never fetch or install artifacts."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manager"))
from hahapent.catalog import load_catalog, validate_catalog  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogs", nargs="*", type=Path, default=[ROOT / "hahapent.json"])
    args = parser.parse_args(argv)
    failed = False
    for path in args.catalogs:
        try:
            errors = validate_catalog(load_catalog(path))
        except (OSError, ValueError, RecursionError):
            print("FAIL: unable to read valid catalog JSON")
            failed = True
            continue
        if errors:
            print("FAIL: catalog metadata")
            for error in errors:
                print("  " + error)
            failed = True
        else:
            print("PASS: catalog metadata (offline only)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

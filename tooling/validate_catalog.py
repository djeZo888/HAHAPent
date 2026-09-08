#!/usr/bin/env python3
"""Validate draft catalog metadata offline; never fetch or install artifacts."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "catalog-v1.schema.json"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def load_catalog(path):
    """Reject ambiguous duplicate keys and nonstandard JSON number constants."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def _safe_https_url(value):
    try:
        parsed = urlsplit(value)
        # Accessing port validates malformed port syntax as well.
        port = parsed.port
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and "\\" not in value
            and not any(character.isspace() for character in value)
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        return False


def _version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def validate_catalog(catalog):
    """Return value-free diagnostics for schema and local semantic errors.

    The input's $schema is metadata only. Validation uses the checked-in schema,
    whose references are local, so an untrusted catalog cannot fetch a schema.
    """
    schema = load_catalog(SCHEMA)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(catalog), key=lambda item: str(list(item.path))):
        path = "/" + "/".join(str(part) for part in error.path)
        # Do not echo invalid values, which could contain credentials.
        errors.append("{}: schema rule {} failed".format(path, error.validator))
    if errors:
        return errors

    source_id = catalog["source"]["id"]
    if not _safe_https_url(catalog["source"]["repository_url"]):
        errors.append(
            "/source/repository_url: expected HTTPS URL without credentials, query or fragment"
        )

    modules = catalog["modules"]
    by_id = {}
    domains = set()
    for index, module in enumerate(modules):
        prefix = "/modules/{}".format(index)
        if module["id"] in by_id:
            errors.append(prefix + "/id: duplicate module identity")
        by_id[module["id"]] = module
        if module["integration_domain"] in domains:
            errors.append(prefix + "/integration_domain: duplicate integration domain")
        domains.add(module["integration_domain"])
        compatibility = module["home_assistant"]
        if "max_version_exclusive" in compatibility and _version_tuple(
            compatibility["max_version_exclusive"]
        ) <= _version_tuple(compatibility["min_version"]):
            errors.append(prefix + "/home_assistant: maximum must be greater than minimum")
        for field in ("artifact", "license", "provenance"):
            url_key = "repository_url" if field == "provenance" else "url"
            if not _safe_https_url(module[field][url_key]):
                errors.append(
                    prefix
                    + "/"
                    + field
                    + "/"
                    + url_key
                    + ": expected HTTPS URL without credentials, query or fragment"
                )
        if any(part in (".", "..") for part in module["provenance"]["source_path"].split("/")):
            errors.append(prefix + "/provenance/source_path: path traversal is forbidden")

    graph = {module_id: set() for module_id in by_id}
    for index, module in enumerate(modules):
        seen_dependencies = set()
        for dependency_index, dependency in enumerate(module["dependencies"]):
            prefix = "/modules/{}/dependencies/{}".format(index, dependency_index)
            identity = (dependency["source_id"], dependency["module_id"])
            if identity in seen_dependencies:
                errors.append(prefix + ": duplicate dependency identity")
            seen_dependencies.add(identity)
            if dependency["source_id"] != source_id:
                # External dependencies require future trusted-source resolution.
                continue
            target = by_id.get(dependency["module_id"])
            if target is None:
                errors.append(prefix + ": local dependency is absent from catalog")
                continue
            if target["version"] != dependency["version"]:
                errors.append(prefix + "/version: local dependency version mismatch")
            if dependency["module_id"] == module["id"]:
                errors.append(prefix + ": module cannot depend on itself")
            graph[module["id"]].add(dependency["module_id"])

    # Kahn's algorithm avoids recursion limits for long dependency chains.
    incoming = {module_id: 0 for module_id in graph}
    for targets in graph.values():
        for target in targets:
            incoming[target] += 1
    ready = [module_id for module_id, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        module_id = ready.pop()
        visited += 1
        for target in graph[module_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if visited != len(graph):
        errors.append("/modules: local dependency cycle")
    return errors


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
            print("PASS: draft catalog metadata (offline only)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

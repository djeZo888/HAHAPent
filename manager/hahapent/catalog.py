"""Strict, bundled JSON contracts and repository identity validation."""

import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from . import __version__

SCHEMA_DIR = next(
    (
        p
        for p in (Path(__file__).parents[1] / "schemas", Path(__file__).parents[2] / "schemas")
        if p.is_dir()
    ),
    Path(__file__).parents[1] / "schemas",
)
FEATURES = frozenset({"versioned-artifacts", "exact-dependencies", "pending-license"})
MAX_JSON_BYTES = 2 * 1024 * 1024


class ManagerError(Exception):
    """Only stable, public error codes cross the application boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def loads_json(value):
    if not isinstance(value, (str, bytes)) or len(value) > MAX_JSON_BYTES:
        raise ValueError("JSON size limit")
    result = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    pending, nodes = [(result, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 64 or nodes > 100000:
            raise ValueError("JSON structure limit")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return result


def load_catalog(path):
    with Path(path).open("rb") as stream:
        return loads_json(stream.read(MAX_JSON_BYTES + 1))


def schema_errors(value, kind):
    if kind not in ("catalog", "settings", "registry", "transaction"):
        raise ManagerError("invalid_schema_kind")
    schema = load_catalog(SCHEMA_DIR / (kind + "-v1.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    # Paths may themselves contain malicious keys. Diagnostics contain no input text.
    errors = []
    pending = list(validator.iter_errors(value))
    while pending:
        error = pending.pop()
        errors.append("schema rule {} failed".format(error.validator))
        pending.extend(error.context)
    return errors


def validate_document(value, kind):
    if isinstance(value, dict) and value.get("schema_version") != 1:
        raise ManagerError("unsupported_schema_version")
    if schema_errors(value, kind):
        raise ManagerError("invalid_" + kind)
    require_features(value)
    return value


def _safe_https_url(value):
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and "\\" not in value
            and not any(c.isspace() or ord(c) < 32 for c in value)
            and (parsed.port is None or parsed.port == 443)
        )
    except (TypeError, ValueError):
        return False


def repository_url(value):
    """Normalize only a public GitHub repository URL; never accept credentials."""
    if not isinstance(value, str) or not _safe_https_url(value):
        raise ManagerError("invalid_repository")
    parsed = urlsplit(value)
    if parsed.hostname != "github.com" or parsed.port is not None:
        raise ManagerError("invalid_repository")
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", path):
        raise ManagerError("invalid_repository")
    if path.split("/")[-1] in (".", ".."):
        raise ManagerError("invalid_repository")
    return "https://github.com" + path


def catalog_url(repository):
    return (
        "https://raw.githubusercontent.com"
        + urlsplit(repository_url(repository)).path
        + "/HEAD/hahapent.json"
    )


def _version_tuple(value):
    return tuple(int(part) for part in value.split("."))


def semver_key(value):
    main, _, _build = value.partition("+")
    core, sep, prerelease = main.partition("-")
    parts = tuple(int(p) for p in core.split("."))
    identifiers = tuple((0, int(p)) if p.isdigit() else (1, p) for p in prerelease.split("."))
    return parts, not bool(sep), identifiers


def require_features(value):
    if semver_key(value.get("minimum_manager_version", "0.1.0")) > semver_key(__version__):
        raise ManagerError("manager_upgrade_required")
    if set(value.get("required_features", [])) - FEATURES:
        raise ManagerError("unsupported_required_feature")


def compatible(module, core_version):
    if not isinstance(core_version, str):
        return False
    try:
        current = _version_tuple(core_version)
        compat = module["home_assistant"]
        return current >= _version_tuple(compat["min_version"]) and (
            "max_version_exclusive" not in compat
            or current < _version_tuple(compat["max_version_exclusive"])
        )
    except (ValueError, TypeError, KeyError):
        return False


def validate_catalog(catalog):
    """Offline diagnostics are deliberately value-free and use only local schemas."""
    errors = schema_errors(catalog, "catalog")
    if errors:
        return errors
    source_id = catalog["source"]["id"]
    if not _safe_https_url(catalog["source"]["repository_url"]):
        errors.append("source: expected HTTPS URL without credentials, query or fragment")
    modules = catalog["modules"]
    by_identity, ids, domains = {}, {}, {}
    for module in modules:
        identity = (module["id"], module["version"])
        if identity in by_identity or (
            module["id"] in ids and ids[module["id"]] != module["integration_domain"]
        ):
            errors.append("duplicate module identity")
        if (
            module["integration_domain"] in domains
            and domains[module["integration_domain"]] != module["id"]
        ):
            errors.append("duplicate integration domain")
        ids[module["id"]] = module["integration_domain"]
        domains[module["integration_domain"]] = module["id"]
        by_identity[identity] = module
        compat = module["home_assistant"]
        if "max_version_exclusive" in compat and _version_tuple(
            compat["max_version_exclusive"]
        ) <= _version_tuple(compat["min_version"]):
            errors.append("maximum must be greater than minimum")
        urls = [
            module["artifact"]["url"],
            module["provenance"]["repository_url"],
            module["documentation_url"],
        ]
        if "url" in module["license"]:
            urls.append(module["license"]["url"])
        if any(not _safe_https_url(url) for url in urls):
            errors.append("expected HTTPS URL without credentials, query or fragment")
        if any(p in (".", "..") for p in module["provenance"]["source_path"].split("/")):
            errors.append("path traversal is forbidden")
    graph = {identity: set() for identity in by_identity}
    for identity, module in by_identity.items():
        seen = set()
        for dep in module["dependencies"]:
            dep_id = (dep["source_id"], dep["module_id"])
            if dep_id in seen:
                errors.append("duplicate dependency identity")
            seen.add(dep_id)
            if dep["source_id"] != source_id:
                continue
            target = (dep["module_id"], dep["version"])
            if dep["module_id"] == module["id"]:
                errors.append("module cannot depend on itself")
            if target not in by_identity:
                errors.append(
                    "local dependency version mismatch"
                    if dep["module_id"] in ids
                    else "local dependency is absent from catalog"
                )
                continue
            graph[identity].add(target)
    incoming = {identity: 0 for identity in graph}
    for targets in graph.values():
        for target in targets:
            incoming[target] += 1
    ready = [identity for identity, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        identity = ready.pop()
        visited += 1
        for target in graph[identity]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if visited != len(graph):
        errors.append("local dependency cycle")
    return errors


def validate_bound_catalog(catalog, repository, expected_source=None):
    if isinstance(catalog, dict) and catalog.get("schema_version") != 1:
        raise ManagerError("unsupported_schema_version")
    if validate_catalog(catalog):
        raise ManagerError("invalid_catalog")
    if (
        repository_url(catalog["source"]["repository_url"]).lower()
        != repository_url(repository).lower()
    ):
        raise ManagerError("source_repository_mismatch")
    if expected_source is not None and catalog["source"]["id"] != expected_source:
        raise ManagerError("source_identity_mismatch")
    require_features(catalog)
    for module in catalog["modules"]:
        if (
            repository_url(module["provenance"]["repository_url"]).lower()
            != repository_url(repository).lower()
        ):
            raise ManagerError("source_repository_mismatch")
        parsed = urlsplit(module["artifact"]["url"])
        prefix = urlsplit(repository_url(repository)).path + "/releases/download/"
        if parsed.hostname != "github.com" or not parsed.path.lower().startswith(prefix.lower()):
            raise ManagerError("artifact_repository_mismatch")
        remainder = parsed.path[len(prefix) :].split("/")
        if len(remainder) != 2 or not all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", p) for p in remainder
        ):
            raise ManagerError("unversioned_artifact")
        tag, name = remainder
        if (
            tag.lower() in ("latest", "main", "master", "head", "develop", "dev")
            or module["version"] not in name
        ):
            raise ManagerError("unversioned_artifact")
    return catalog

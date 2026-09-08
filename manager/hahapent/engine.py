"""Serialized integration lifecycle with persisted ownership and crash recovery."""

import copy
import fcntl
import json
import os
import stat
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .catalog import (
    MAX_JSON_BYTES,
    ManagerError,
    catalog_url,
    compatible,
    load_catalog,
    loads_json,
    repository_url,
    require_features,
    validate_bound_catalog,
    validate_document,
)
from .downloads import MAX_ARTIFACT_BYTES, Downloader, extract_artifact
from .storage import (
    atomic_json,
    copy_owned,
    fsync_dir,
    hash_tree,
    no_symlink,
    read_document,
    remove_owned,
    sync_tree,
    verify_tree,
)

DEFAULT_SETTINGS = {"schema_version": 1, "extra_repositories": [], "extensions": {}}
DEFAULT_REGISTRY = {"schema_version": 1, "installed": {}, "removed": {}, "extensions": {}}


class Manager:
    def __init__(
        self,
        data_dir,
        config_dir,
        ha_adapter=None,
        downloader=None,
        builtin_catalog=None,
        test_catalog=None,
    ):
        self.data = Path(data_dir).absolute()
        self.config = Path(config_dir).absolute()
        no_symlink(self.data)
        no_symlink(self.config)
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.config.is_dir():
            raise ManagerError("configuration_mount_unavailable")
        self.components = self.config / "custom_components"
        no_symlink(self.components)
        self.settings_path = self.data / "settings.json"
        self.registry_path = self.data / "registry.json"
        self.journal_path = self.data / "transaction.json"
        self.builtin_cache_path = self.data / "builtin-catalog-cache.json"
        self.backups = self.data / "backups"
        no_symlink(self.backups)
        self.backups.mkdir(exist_ok=True, mode=0o700)
        self.ha = ha_adapter
        self.downloader = downloader or Downloader()
        self.builtin_catalog = builtin_catalog or Path(__file__).parents[1] / "hahapent.json"
        self.test_catalog = test_catalog
        self._lock = threading.Lock()
        self.catalogs = {}
        self.source_states = {}
        self.operation = {"state": "idle"}
        self.recovery = {"state": "clean"}
        with self._serialized():
            self._load_state()
            self._recover()
            self._refresh_catalogs()

    @contextmanager
    def _serialized(self):
        if not self._lock.acquire(blocking=False):
            raise ManagerError("operation_in_progress")
        descriptor = None
        try:
            no_symlink(self.data / "manager.lock")
            descriptor = os.open(str(self.data / "manager.lock"), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ManagerError("operation_in_progress") from None
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self._lock.release()

    def _load_state(self):
        self.settings = read_document(
            self.settings_path, "settings", copy.deepcopy(DEFAULT_SETTINGS)
        )
        self.registry = read_document(
            self.registry_path, "registry", copy.deepcopy(DEFAULT_REGISTRY)
        )
        # Schema validation is not enough for identity/path-bearing persistent data.
        seen_ids, seen_repos = set(), set()
        for source in self.settings["extra_repositories"]:
            repo = repository_url(source["repository_url"]).lower()
            if source["source_id"] in seen_ids or repo in seen_repos:
                raise ManagerError("invalid_settings")
            seen_ids.add(source["source_id"])
            seen_repos.add(repo)
        self._validate_registry(self.registry)

    def _validate_registry(self, registry):
        for domain, entry in registry["installed"].items():
            if entry["module"]["integration_domain"] != domain:
                raise ManagerError("invalid_registry")
            repository_url(entry["repository_url"])
            self._validate_files(entry["files"])
            if "previous" in entry:
                self._validate_backup(domain, entry["previous"])
        for domain, backup in registry["removed"].items():
            self._validate_backup(domain, backup)

    def _validate_files(self, files):
        for name in files:
            if name.startswith("/") or any(
                p in ("", ".", "..") for p in name.rstrip("/").split("/")
            ):
                raise ManagerError("invalid_registry")

    def _validate_backup(self, domain, backup):
        if backup["entry"]["module"]["integration_domain"] != domain:
            raise ManagerError("invalid_registry")
        self._validate_files(backup["entry"]["files"])

    def _download(self, url, maximum):
        try:
            method = getattr(self.downloader, "download", self.downloader)
            result = method(url, max_bytes=maximum)
            if not isinstance(result, bytes) or len(result) > maximum:
                raise ManagerError("download_too_large")
            return result
        except ManagerError:
            raise
        except Exception:
            raise ManagerError("download_failed") from None

    def _read_catalog(self, value):
        try:
            return copy.deepcopy(value) if isinstance(value, dict) else load_catalog(value)
        except (ValueError, OSError, RecursionError):
            raise ManagerError("invalid_catalog") from None

    def _base_catalog(self, value):
        catalog = self._read_catalog(value)
        try:
            repo = catalog["source"]["repository_url"]
        except (KeyError, TypeError):
            raise ManagerError("invalid_catalog") from None
        return validate_bound_catalog(catalog, repo)

    def refresh_catalogs(self):
        with self._serialized():
            self._load_state()
            self._recover()
            self._refresh_catalogs(fetch_builtin=True)
        return self.status()

    def _load_builtin_cache(self, repository, source_id):
        """Revalidate persisted metadata against the immutable bundled identity."""
        no_symlink(self.builtin_cache_path)
        try:
            metadata = self.builtin_cache_path.stat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ManagerError("invalid_catalog_cache")
        cache = load_catalog(self.builtin_cache_path)
        if (
            not isinstance(cache, dict)
            or cache.keys() != {"schema_version", "fetched_at", "catalog"}
            or type(cache["schema_version"]) is not int
            or cache["schema_version"] != 1
            or not isinstance(cache["fetched_at"], str)
        ):
            raise ManagerError("invalid_catalog_cache")
        fetched_at = datetime.fromisoformat(cache["fetched_at"])
        if fetched_at.tzinfo != timezone.utc:
            raise ManagerError("invalid_catalog_cache")
        validate_bound_catalog(cache["catalog"], repository, source_id)
        return cache

    def _refresh_builtin(self, bundled, fetch_remote):
        """Select validated metadata; failed refreshes never replace a good cache."""
        source_id = bundled["source"]["id"]
        repository = bundled["source"]["repository_url"]
        catalog = bundled
        state = {
            **bundled["source"],
            "builtin": True,
            "available": True,
            "catalog_origin": "bundled",
            "refresh_status": "not_checked",
            "last_successful_refresh": None,
            "last_refresh_attempt": None,
        }
        cache_writable = True
        try:
            cache = self._load_builtin_cache(repository, source_id)
            if cache is not None:
                catalog = cache["catalog"]
                state.update(
                    name=catalog["source"]["name"],
                    catalog_origin="cache",
                    last_successful_refresh=cache["fetched_at"],
                )
        except (OSError, ValueError, RecursionError, ManagerError):
            # Preserve malformed/future cache documents for explicit recovery.
            # Do not read through unsafe paths or rewrite an unknown format.
            cache_writable = False
            state["cache_error"] = "invalid_catalog_cache"
        previous = self.source_states.get(source_id, {})
        if previous.get("builtin") and source_id in self.catalogs:
            prior = self.catalogs[source_id]
            validate_bound_catalog(prior, repository, source_id)
            if (previous.get("last_successful_refresh") or "") >= (
                state["last_successful_refresh"] or ""
            ):
                catalog = prior
                state = {
                    **previous,
                    **({"cache_error": state["cache_error"]} if "cache_error" in state else {}),
                }
        if not fetch_remote:
            return catalog, state
        attempt = datetime.now(timezone.utc).isoformat()
        state.update(last_refresh_attempt=attempt, refresh_status="failed")
        try:
            candidate = loads_json(self._download(catalog_url(repository), MAX_JSON_BYTES))
            validate_bound_catalog(candidate, repository, source_id)
            if not cache_writable:
                raise ManagerError("invalid_catalog_cache")
            cache = {"schema_version": 1, "fetched_at": attempt, "catalog": candidate}
            # The envelope must obey the same bounded JSON reader on restart.
            serialized = json.dumps(cache, ensure_ascii=True, separators=(",", ":"))
            if len(serialized.encode()) + 1 > MAX_JSON_BYTES:
                raise ManagerError("catalog_cache_too_large")
            loads_json(serialized)
            try:
                atomic_json(self.builtin_cache_path, cache, compact=True)
            except (OSError, ValueError, ManagerError):
                raise ManagerError("catalog_cache_write_failed") from None
            catalog = candidate
            state.update(
                name=candidate["source"]["name"],
                catalog_origin="remote",
                refresh_status="success",
                last_successful_refresh=attempt,
            )
            state.pop("error", None)
            state.pop("cache_error", None)
        except (ValueError, RecursionError):
            state["error"] = "invalid_catalog"
        except ManagerError as error:
            state["error"] = error.code
        return catalog, state

    def _refresh_catalogs(self, *, fetch_builtin=False):
        catalogs, states = {}, {}
        builtin = self._base_catalog(self.builtin_catalog)
        builtin_id = builtin["source"]["id"]
        catalogs[builtin_id], states[builtin_id] = self._refresh_builtin(builtin, fetch_builtin)
        if self.settings.get("test_mode", False):
            if self.test_catalog is None:
                raise ManagerError("test_catalog_unavailable")
            test = self._base_catalog(self.test_catalog)
            test_id = test["source"]["id"]
            if test_id in catalogs:
                raise ManagerError("source_identity_conflict")
            catalogs[test_id] = test
            states[test_id] = {
                **test["source"],
                "builtin": True,
                "test_only": True,
                "available": True,
            }
        for source in self.settings["extra_repositories"]:
            sid, repo = source["source_id"], source["repository_url"]
            if sid in catalogs:
                raise ManagerError("source_identity_conflict")
            state = {
                "id": sid,
                "name": sid,
                "repository_url": repo,
                "builtin": False,
                "available": False,
            }
            try:
                catalog = loads_json(self._download(catalog_url(repo), MAX_JSON_BYTES))
                validate_bound_catalog(catalog, repo, sid)
                catalogs[sid] = catalog
                state.update(name=catalog["source"]["name"], available=True)
            except (ValueError, RecursionError):
                state["error"] = "invalid_catalog"
            except ManagerError as error:
                state["error"] = error.code
            states[sid] = state
        self.catalogs, self.source_states = catalogs, states

    def _ha_call(self, method, *args):
        if self.ha is None or not callable(getattr(self.ha, method, None)):
            raise ManagerError("ha_status_unavailable")
        try:
            return getattr(self.ha, method)(*args)
        except ManagerError:
            raise
        except Exception:
            raise ManagerError("ha_status_unavailable") from None

    def _domain_state(self, domain, entry):
        try:
            details = self._ha_call("domain_status", domain)
            if not isinstance(details, dict) or not isinstance(details.get("configured"), bool):
                raise ManagerError("ha_status_unavailable")
            restart = entry["restart_pending"]
            if (
                details.get("loaded") is True
                and details.get("loaded_version") == entry["module"]["version"]
            ):
                restart = False
            return {
                "configured": details["configured"],
                "loaded": details.get("loaded", False),
                "loaded_version": details.get("loaded_version"),
                "restart_pending": restart,
            }
        except ManagerError:
            return {
                "configured": None,
                "loaded": None,
                "loaded_version": None,
                "restart_pending": entry["restart_pending"],
                "ha_status": "unavailable",
            }

    def status(self):
        # Copy immutable snapshots; long download jobs may be running on another thread.
        settings = copy.deepcopy(self.settings)
        registry = copy.deepcopy(self.registry)
        catalogs = copy.deepcopy(self.catalogs)
        try:
            core = self._ha_call("core_version")
        except ManagerError:
            core = None
        modules = []
        for source_id, catalog in catalogs.items():
            for module in catalog["modules"]:
                installed = registry["installed"].get(module["integration_domain"])
                try:
                    require_features(module)
                    supported = True
                except ManagerError:
                    supported = False
                modules.append(
                    {
                        **copy.deepcopy(module),
                        "source_id": source_id,
                        "source_name": catalog["source"]["name"],
                        "compatible": supported and compatible(module, core),
                        "installed_version": installed["module"]["version"] if installed else None,
                    }
                )
        installed_rows = []
        for domain, entry in registry["installed"].items():
            installed_rows.append(
                {
                    "domain": domain,
                    "source_id": entry["source_id"],
                    "repository_url": entry["repository_url"],
                    "module": entry["module"],
                    "version": entry["module"]["version"],
                    "files_installed": True,
                    "rollback_available": "previous" in entry,
                    "source_available": entry["source_id"] in catalogs,
                    **self._domain_state(domain, entry),
                }
            )
        return {
            "manager_version": __version__,
            "core_version": core,
            "settings": settings,
            "sources": copy.deepcopy(list(self.source_states.values())),
            "modules": modules,
            "installed": installed_rows,
            "operation": copy.deepcopy(self.operation),
            "recovery": {
                **copy.deepcopy(self.recovery),
                "removed": [
                    {
                        "domain": domain,
                        "version": backup["entry"]["module"]["version"],
                        "rollback_available": True,
                        "restart_pending": backup.get("restart_pending", True),
                    }
                    for domain, backup in registry["removed"].items()
                ],
            },
        }

    def add_source(self, repository, trusted=False):
        if trusted is not True:
            raise ManagerError("source_trust_required")
        repo = repository_url(repository)
        with self._serialized():
            self._load_state()
            self._recover()
            try:
                catalog = loads_json(self._download(catalog_url(repo), MAX_JSON_BYTES))
            except (ValueError, RecursionError):
                raise ManagerError("invalid_catalog") from None
            validate_bound_catalog(catalog, repo)
            source_id = catalog["source"]["id"]
            if source_id in self.source_states or any(
                repository_url(source["repository_url"]).lower() == repo.lower()
                for source in self.source_states.values()
            ):
                raise ManagerError("source_identity_conflict")
            # Retained installed ownership may not be rebound by removing/readding a source.
            entries = list(self.registry["installed"].values()) + [
                b["entry"] for b in self.registry["removed"].values()
            ]
            if any(
                e["source_id"] == source_id
                and repository_url(e["repository_url"]).lower() != repo.lower()
                for e in entries
            ):
                raise ManagerError("source_identity_conflict")
            settings = copy.deepcopy(self.settings)
            settings["extra_repositories"].append(
                {"source_id": source_id, "repository_url": repo, "trusted": True}
            )
            validate_document(settings, "settings")
            atomic_json(self.settings_path, settings)
            self.settings = settings
            self._refresh_catalogs()
        return self.status()

    def remove_source(self, source_id):
        with self._serialized():
            self._load_state()
            self._recover()
            settings = copy.deepcopy(self.settings)
            sources = settings["extra_repositories"]
            settings["extra_repositories"] = [
                source for source in sources if source["source_id"] != source_id
            ]
            if len(sources) == len(settings["extra_repositories"]):
                raise ManagerError("source_not_removable")
            atomic_json(self.settings_path, settings)
            self.settings = settings
            self._refresh_catalogs()
        return self.status()

    def set_test_mode(self, enabled):
        if not isinstance(enabled, bool):
            raise ManagerError("invalid_request")
        with self._serialized():
            self._load_state()
            self._recover()
            if enabled:
                if self.test_catalog is None:
                    raise ManagerError("test_catalog_unavailable")
                self._base_catalog(self.test_catalog)
            settings = copy.deepcopy(self.settings)
            settings["test_mode"] = enabled
            atomic_json(self.settings_path, settings)
            self.settings = settings
            self._refresh_catalogs()
        return self.status()

    def _resolve(self, source_id, module_id, version):
        catalog = self.catalogs.get(source_id)
        if catalog is None:
            raise ManagerError("source_unavailable")
        require_features(catalog)
        for module in catalog["modules"]:
            if module["id"] == module_id and module["version"] == version:
                require_features(module)
                return copy.deepcopy(module), catalog["source"]["repository_url"]
        raise ManagerError("module_version_unavailable")

    def _check_compatibility(self, module):
        if not compatible(module, self._ha_call("core_version")):
            raise ManagerError("ha_version_incompatible")
        core = self._ha_call("is_core_domain", module["integration_domain"])
        if core is not False:
            raise ManagerError(
                "core_ownership_conflict" if core is True else "ha_status_unavailable"
            )
        require_features(module)

    def _check_dependencies(self, module, replacing_domain=None):
        for dependency in module["dependencies"]:
            matches = [
                entry
                for entry in self.registry["installed"].values()
                if entry["source_id"] == dependency["source_id"]
                and entry["module"]["id"] == dependency["module_id"]
                and entry["module"]["version"] == dependency["version"]
            ]
            if len(matches) != 1 or matches[0]["module"]["integration_domain"] == replacing_domain:
                raise ManagerError("dependency_unmet")
            self._check_compatibility(matches[0]["module"])
            verify_tree(
                self.components / matches[0]["module"]["integration_domain"], matches[0]["files"]
            )
        for entry in self.registry["installed"].values():
            if entry["module"]["integration_domain"] == replacing_domain:
                continue
            for dependency in entry["module"]["dependencies"]:
                if (
                    dependency["module_id"] == module["id"]
                    and dependency["version"] != module["version"]
                ):
                    current = self.registry["installed"].get(replacing_domain)
                    if current and dependency["source_id"] == current["source_id"]:
                        raise ManagerError("installed_dependent_conflict")

    def _check_native_dependencies(self, manifest, module):
        declared = {(dep["source_id"], dep["module_id"]) for dep in module["dependencies"]}
        for domain in manifest.get("dependencies", []) + manifest.get("after_dependencies", []):
            if self._ha_call("is_core_domain", domain) is True:
                continue
            entry = self.registry["installed"].get(domain)
            if entry is None or (entry["source_id"], entry["module"]["id"]) not in declared:
                raise ManagerError("undeclared_native_dependency")

    def _check_target(self, domain, source_id=None, repository=None):
        target = self.components / domain
        no_symlink(target)
        current = self.registry["installed"].get(domain)
        if current:
            if source_id is not None and (
                current["source_id"] != source_id
                or repository_url(current["repository_url"]).lower()
                != repository_url(repository).lower()
            ):
                raise ManagerError("ownership_conflict")
            verify_tree(target, current["files"])
        elif target.exists():
            raise ManagerError("ownership_conflict")
        return current

    def install(self, source_id, module_id, version):
        with self._serialized():
            self._load_state()
            self._recover()
            module, repo = self._resolve(source_id, module_id, version)
            domain = module["integration_domain"]
            self._check_compatibility(module)
            current = self._check_target(domain, source_id, repo)
            if current and current["module"]["id"] != module_id:
                raise ManagerError("ownership_conflict")
            if current and current["module"]["version"] == version:
                raise ManagerError("already_installed")
            self._check_dependencies(module, domain)
            self.operation = {
                "state": "running",
                "action": "update" if current else "install",
                "phase": "downloading",
            }
            try:
                content = self._download(module["artifact"]["url"], MAX_ARTIFACT_BYTES)
                self._change(
                    domain, self.operation["action"], module, source_id, repo, content=content
                )
            except ManagerError as error:
                self.operation = {"state": "failed", "error": error.code}
                raise
            except OSError:
                self.operation = {"state": "failed", "error": "storage_failure"}
                raise ManagerError("storage_failure") from None
        return self.status()

    def rollback(self, domain):
        with self._serialized():
            self._load_state()
            self._recover()
            current = self.registry["installed"].get(domain)
            previous = current.get("previous") if current else self.registry["removed"].get(domain)
            if not previous:
                raise ManagerError("rollback_unavailable")
            self._check_target(domain)
            entry = previous["entry"]
            self._check_compatibility(entry["module"])
            self._check_dependencies(entry["module"], domain)
            backup = self.backups / previous["backup_id"]
            verify_tree(backup, entry["files"])
            self.operation = {"state": "running", "action": "rollback", "phase": "staging"}
            self._change(
                domain,
                "rollback",
                entry["module"],
                entry["source_id"],
                entry["repository_url"],
                backup=(backup, entry["files"]),
            )
        return self.status()

    def _require_no_config_entries(self, domain):
        entries = self._ha_call("config_entries", domain)
        if not isinstance(entries, list):
            raise ManagerError("ha_status_unavailable")
        if entries:
            raise ManagerError("remove_native_config_entries_first")

    def remove(self, domain, confirmed=False):
        if confirmed is not True:
            raise ManagerError("removal_confirmation_required")
        with self._serialized():
            self._load_state()
            self._recover()
            current = self.registry["installed"].get(domain)
            if current is None:
                raise ManagerError("module_not_installed")
            self._check_target(domain)
            self._require_no_config_entries(domain)
            for entry in self.registry["installed"].values():
                if any(
                    dep["source_id"] == current["source_id"]
                    and dep["module_id"] == current["module"]["id"]
                    for dep in entry["module"]["dependencies"]
                ):
                    raise ManagerError("installed_dependent_conflict")
            self.operation = {"state": "running", "action": "remove", "phase": "backing_up"}
            self._change(domain, "remove", None, None, None)
        return self.status()

    def _paths(self, transaction):
        identity = transaction["transaction_id"]
        return (
            self.components / transaction["domain"],
            self.components / (".hahapent-stage-" + identity),
            self.components / (".hahapent-hold-" + identity),
        )

    def _journal(self, transaction, phase):
        transaction["phase"] = phase
        validate_document(transaction, "transaction")
        atomic_json(self.journal_path, transaction)
        self.operation["phase"] = phase

    @staticmethod
    def _base_entry(entry):
        value = copy.deepcopy(entry)
        value.pop("previous", None)
        return value

    def _change(self, domain, action, module, source_id, repo, content=None, backup=None):
        self.components.mkdir(exist_ok=True, mode=0o755)
        no_symlink(self.components)
        before = copy.deepcopy(self.registry)
        current = before["installed"].get(domain)
        transaction = {
            "schema_version": 1,
            "transaction_id": uuid.uuid4().hex,
            "domain": domain,
            "operation": action,
            "phase": "prepared",
            "before": before,
            "after": copy.deepcopy(before),
        }
        target, stage, hold = self._paths(transaction)
        for path in (target, stage, hold):
            no_symlink(path)
        if stage.exists() or hold.exists():
            raise ManagerError("transaction_path_conflict")
        try:
            self._journal(transaction, "prepared")
            if module is not None:
                if backup:
                    copy_owned(backup[0], stage, backup[1])
                    try:
                        manifest = load_catalog(stage / "manifest.json")
                    except (ValueError, OSError, RecursionError):
                        raise ManagerError("invalid_manifest") from None
                    self._check_native_dependencies(manifest, module)
                else:
                    stage.mkdir(mode=0o755)
                    manifest = extract_artifact(content, stage, module)
                    self._check_native_dependencies(manifest, module)
                hashes = hash_tree(stage)
                sync_tree(stage)
                entry = {
                    "source_id": source_id,
                    "repository_url": repo,
                    "module": copy.deepcopy(module),
                    "files": hashes,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                    "transaction_id": transaction["transaction_id"],
                    "restart_pending": module["restart"]["home_assistant"] != "not_required",
                    "extensions": copy.deepcopy(current.get("extensions", {})) if current else {},
                }
            else:
                entry = None
            previous = None
            if current:
                previous = {
                    "backup_id": transaction["transaction_id"],
                    "entry": self._base_entry(current),
                }
                copy_owned(target, self.backups / previous["backup_id"], current["files"])
            after = transaction["after"]
            if entry is None:
                del after["installed"][domain]
                previous["restart_pending"] = True
                after["removed"][domain] = previous
            else:
                if previous:
                    entry["previous"] = previous
                after["installed"][domain] = entry
                after["removed"].pop(domain, None)
            validate_document(after, "registry")
            self._journal(transaction, "staged")
            # Recheck immediately before replacing; sources changing never confer ownership.
            self._check_target(domain, source_id if module else None, repo)
            if action == "remove":
                # Native setup can change during the backup. Recheck at the swap
                # boundary; never remove code after a newly created config entry.
                self._require_no_config_entries(domain)
            if current:
                os.replace(str(target), str(hold))
                fsync_dir(self.components)
            self._journal(transaction, "old_moved")
            if module is not None:
                os.replace(str(stage), str(target))
                fsync_dir(self.components)
            self._journal(transaction, "new_moved")
            atomic_json(self.registry_path, after)
            self.registry = after
            self._journal(transaction, "committed")
            self._finish(transaction)
            self.operation = {
                "state": "succeeded",
                "action": action,
                "phase": "complete",
                "domain": domain,
                "restart_pending": entry["restart_pending"] if entry else True,
            }
        except (ManagerError, OSError) as error:
            code = error.code if isinstance(error, ManagerError) else "storage_failure"
            try:
                self._load_state()
                self._recover()
            except (ManagerError, OSError):
                self.recovery = {"state": "required", "error": "recovery_required"}
                self.operation = {"state": "failed", "error": "recovery_required"}
                raise ManagerError("recovery_required") from None
            self.operation = {"state": "failed", "error": code}
            raise ManagerError(code) from None

    def _remove_stage(self, stage):
        if stage.exists() or stage.is_symlink():
            remove_owned(stage, hash_tree(stage))

    def _finish(self, transaction):
        target, stage, hold = self._paths(transaction)
        domain = transaction["domain"]
        after_entry = transaction["after"]["installed"].get(domain)
        old_entry = transaction["before"]["installed"].get(domain)
        if after_entry:
            verify_tree(target, after_entry["files"])
        elif target.exists() or target.is_symlink():
            raise ManagerError("recovery_required")
        if hold.exists() or hold.is_symlink():
            if old_entry is None:
                raise ManagerError("recovery_required")
            remove_owned(hold, old_entry["files"])
        self._remove_stage(stage)
        self.journal_path.unlink()
        fsync_dir(self.data)

    def _recover(self):
        if not self.journal_path.exists() and not self.journal_path.is_symlink():
            return
        transaction = read_document(self.journal_path, "transaction")
        self._validate_registry(transaction["before"])
        self._validate_registry(transaction["after"])
        target, stage, hold = self._paths(transaction)
        for path in (target, stage, hold):
            no_symlink(path)
        domain = transaction["domain"]
        before = transaction["before"]["installed"].get(domain)
        after = transaction["after"]["installed"].get(domain)
        # The registry is the commit point. Journal phase may lag an atomic write.
        if self.registry == transaction["after"] and transaction["after"] != transaction["before"]:
            self._finish(transaction)
            self.recovery = {"state": "recovered", "result": "committed"}
            return
        if self.registry != transaction["before"]:
            raise ManagerError("recovery_required")
        if hold.exists():
            if before is None:
                raise ManagerError("recovery_required")
            verify_tree(hold, before["files"])
            if target.exists():
                if after is None or after == before:
                    raise ManagerError("recovery_required")
                remove_owned(target, after["files"])
            os.replace(str(hold), str(target))
            fsync_dir(self.components)
        elif before is not None:
            verify_tree(target, before["files"])
        elif target.exists():
            if after is None:
                raise ManagerError("recovery_required")
            remove_owned(target, after["files"])
        self._remove_stage(stage)
        # Registry was never committed, so restoring it is unnecessary and would
        # itself require free disk space. The old JSON remains byte-for-byte valid.
        self.journal_path.unlink()
        fsync_dir(self.data)
        self.recovery = {"state": "recovered", "result": "rolled_back"}

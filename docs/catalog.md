# Catalog and persistent JSON contract

HAHAPent 0.1.2 reads three independent JSON v1 contracts: source catalogs,
Manager settings and the installed registry. Manager releases and integration
versions are separate SemVer values. The Manager uses its bundled JSON Schemas;
a document's `$schema` never causes a network request.

Canonical schemas and defaults are in `schemas/`. The Supervisor build context
contains byte-identical schema/catalog copies in `manager/`, maintained by
`python tooling/sync_manager_bundle.py`; CI checks for drift. The normal
`hahapent.json` includes the explicitly read-only Aquarius prerelease candidate;
its description and module documentation identify the blocked control/lifecycle work.
Manager 0.1.2 can refresh this source from canonical GitHub metadata and persists
its validated last-known-good catalog. Older Manager 0.1.1 reads only its installed
bundle and needs the targeted App update before it can discover later module releases.
The device-free Task 002 fixture has a separate catalog and explicit test-mode
switch. Enabling a catalog or adding a source never installs its code.

## Draft-to-release transition

Task 001's v1 was an **unreleased metadata draft**, not an installed-state format.
This release finalizes that same version, adding descriptions, documentation,
capability gates and optional extensions. The original empty document with
`schema_version: 1`, `status: "draft"`, `source` and `modules: []` remains readable
without rewriting it. A nonempty draft is rejected; published modules require
`status: "released"` and the release contract. There is no invented v2 migration.

Duplicate JSON keys, non-finite numbers, malformed or unknown properties outside
`extensions`, and unsupported future schema versions fail closed. Existing
settings, registry or transaction bytes are not overwritten on a validation
failure. Future breaking formats require an explicit, backed-up migration with
old/new fixtures and interruption tests before support is added.

## Source catalogs

A released source has this shape (this minimal example omits module entries):

```json
{
  "schema_version": 1,
  "status": "released",
  "minimum_manager_version": "0.1.0",
  "required_features": [],
  "source": {
    "id": "example-suite",
    "name": "Example suite",
    "repository_url": "https://github.com/example/suite"
  },
  "modules": [],
  "extensions": {}
}
```

A module describes `id`, `name`, `description`, `documentation_url`,
`integration_domain`, independent `version`, `minimum_manager_version`,
`required_features`, `home_assistant`, exact `dependencies`, `artifact`,
`provenance`, `license` and `restart`. See the schema and the synthetic complete
example at `tests/fixtures/catalog/valid-synthetic.json`.

- `home_assistant.min_version` is inclusive; `max_version_exclusive` is optional.
  A maximum must be greater than the minimum. Unknown current HA compatibility
  blocks installation but does not hide installed entries.
- An artifact supplies `format: "zip"`, an HTTPS `url` and lowercase `sha256`.
  Runtime installations accept a versioned asset under the approved repository's
  `/releases/download/<tag>/<filename>` path. The filename contains the module
  version. Branch archives and moving labels such as `main` or `latest` are
  rejected. A Manager or fixture release tag need not equal the module version.
- Provenance includes the same approved `repository_url`, a full 40-character
  commit `revision` and a relative `source_path`. Provenance records publisher
  assertions; a digest verifies bytes, not publisher trust.
- A source may list multiple versions of the same module and domain. A repeated
  `(id, version)`, a domain assigned to different IDs or one ID mapped to different
  domains is invalid. Source identity cannot be rebound to a different repository,
  including after removal while installed or recoverable code remains.
- Dependencies identify `source_id`, `module_id` and one exact `version`.
  Local catalog references must exist and be acyclic. Installation requires those
  exact, compatible, unmodified Manager-owned versions already installed. No
  dependency solver or automatic installation runs. Updates/removals that break
  an installed dependent are blocked. Native custom integration dependencies
  must be declared; built-in HA dependencies are checked through HA.
- The initial runtime supports pure-Python integrations with empty native
  `requirements`. Nonempty Python package requirements are rejected; adding
  support requires explicit capability negotiation and dependency validation.
- `restart.home_assistant` and `restart.manager` use `required`, `not_required` or
  `unknown`. Installed files, pending Core restart and native configuration are
  separate states. The Manager never restarts Core itself. Its restart indicator
  clears only when HA reports the matching version loaded.
- An identified license uses `expression` and `url`. When the owner's license
  decision is still pending, use `{"status": "pending"}`; do not invent a license
  or URL. This is the built-in fixture's state.

Extra sources require an explicit trust acknowledgment for an HTTPS public GitHub
repository, with no embedded credentials, query or fragment. Catalog metadata is
read from that repository's `HEAD/hahapent.json`; module code always comes from
selected versioned release artifacts. Refreshing metadata never updates code.
A source may be removed while its code remains installed. Offline or removed
sources do not erase the registry, documentation, previous code or removal option.

## Built-in refresh and cache

The built-in source identity and repository are anchored to the bundled catalog.
An explicit **Refresh catalogs** downloads that exact repository's
`HEAD/hahapent.json` through the existing bounded HTTPS downloader. Source identity,
repository/artifact binding, schema and Manager feature requirements must all
validate before metadata replaces the last usable catalog. This operation never
installs code or restarts HA. Extra-source refresh and duplicate-source guards
remain unchanged; the built-in repository cannot be added again as an extra source.

A successful download is persisted atomically with mode `0600` in the App's
`/data/builtin-catalog-cache.json` before activation. The cache has an internal
v1 envelope containing exactly `schema_version`, UTC `fetched_at`, and `catalog`.
The complete envelope obeys the existing JSON byte/depth/node limits. On startup,
the cache is read and revalidated against the bundled identity without a remote
built-in fetch; missing or unusable cache data falls back to the bundled catalog.
Invalid, unsafe, or future cache files remain unchanged for explicit recovery.

The source status reports `catalog_origin` (`bundled`, `cache`, or `remote`),
`refresh_status` (`not_checked`, `success`, or `failed`), the persisted
`last_successful_refresh`, and the current session's `last_refresh_attempt`.
Sanitized `error` and `cache_error` fields identify failures. Cached metadata remains
available after a failed download; an old timestamp does not establish freshness.
Unknown schemas/features, malformed metadata, identity changes, and cache-write
failures never replace the previously usable catalog. Sources renders these
details and a failed refresh also shows a notice in the catalog view.

## Capability and extension rules

Optional `extensions` objects hold opaque JSON for other readers at catalog,
source, module and relevant nested/persistent levels. Unknown extension contents
are preserved when their owning settings or registry objects are saved; they
never enable code, bypass validation or change required behavior.

Catalogs and modules explicitly require `minimum_manager_version` and
`required_features`. Settings/registry may also declare these gates; their
absence means the documented initial v1 behavior. A reader must reject a greater
minimum or unknown required feature. Initial feature names are
`versioned-artifacts`, `exact-dependencies` and `pending-license`. They describe
implemented behavior; listing them cannot turn safeguards off. SemVer prerelease
ordering is honored, and build metadata does not affect comparison.

## Settings

The persistent default is:

```json
{"schema_version": 1, "extra_repositories": [], "extensions": {}}
```

An approved extra source is stored as
`{"source_id":"example-suite","repository_url":"https://github.com/example/suite","trusted":true}`.
Optional `test_mode` controls only the separate fixture catalog. It survives App
restarts and is disabled at the end of the test lifecycle. Settings contain no
owner credentials. Source removal changes only this list.

## Installed registry and recovery

The initial registry is:

```json
{"schema_version": 1, "installed": {}, "removed": {}, "extensions": {}}
```

`installed` is keyed by integration domain. Each entry preserves source/repository,
complete selected module metadata, per-file SHA-256 values and directory markers,
installation time, transaction ID, restart requirement and optional extensions.
`previous` points to an App-data backup plus the prior entry. `removed` retains
recoverable removal backups and an optional `restart_pending` warning, set true
on removal. The warning survives App restart; older v1 removal records without
it are interpreted conservatively as pending. The initial release cannot prove
a Core restart after removal, so this warning remains until code is restored
or a future explicitly verified observation clears it; it is not a claim that
removed code is still loaded. Paths to backups are derived solely from validated
random IDs, never from catalog text. Backups are retained privately; v0.1.x has
no automatic backup pruning, so operators should monitor App-data free space.

Every mutation takes an in-process lock and an OS file lock, validates ownership,
stages one domain, and uses a persisted `transaction-v1.schema.json` journal.
Files and directories are flushed, JSON is written through a private temporary
file and atomic replacement, and domain directories are swapped on the same
filesystem. Prior code is copied and verified in App data before replacement or
removal. The atomic registry write is the commit point. On startup, an interrupted
precommit transaction restores prior code; a committed one finishes cleanup.
Rollback does not require a new registry write while disk-full recovery restores
an uncommitted operation. Unexpected changed paths stop recovery for review.

Ownership includes additional, missing and modified files/directories, with links
and special files rejected. HA-generated `__pycache__/*.pyc` with an owned source counterpart are the sole generated
cache allowance: they are excluded from code hashes and backups, never followed
through links, and discarded with owned code. Any other extra cache contents or
extra integration files block a replacement. Core, HACS and manually installed
code is never adopted or overwritten.

The ZIP must contain exactly one `custom_components/<domain>/` integration with
case-exact `manifest.json` and `__init__.py`; the manifest's domain/version must
match the selected metadata. Extraction rejects traversal, escaping paths,
case aliases, duplicate entries, links, special files, unsupported compression,
corruption, packaged bytecode/cache files and oversized input. Limits are 32 MiB downloaded, 64 MiB extracted,
8 MiB per file and 2,000 archive members. Catalog JSON is at most 2 MiB. Download
DNS, headers and body share a 30-second default deadline, verified HTTPS and public
IP checks. Only GitHub and exact GitHub release-asset redirect hosts are accepted;
no credential or proxy headers are forwarded. Install scripts are never executed.

Removal requires confirmation and zero native HA config entries for the domain;
users remove entries in HA's native integration interface first. The entry check
is repeated immediately before the directory swap, after backing up code. The Manager does
not modify `.storage`, YAML configuration or device settings. Code rollback also
cannot undo HA configuration migrations or device settings. Installed integrations
run directly in HA Core, with no Manager or developer-computer service dependency.

## Offline validation

```sh
.venv/bin/python tooling/validate_catalog.py
.venv/bin/python -m unittest tests.test_catalog tests.test_manager_contracts \
  tests.test_manager_engine tests.test_manager_downloads
```

These use synthetic URLs, mocked downloads/HA adapters and temporary directories.
They validate contracts and failure handling; live deployment and UI evidence
are recorded separately in `tasks/002-suite-manager.md`.

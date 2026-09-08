# Development

## Local setup

Use Python 3.9 or newer in an isolated `.venv`. Keep the environment and caches
out of Git. Dependency versions are pinned in the repository's development
requirements. Public CI runs only synthetic inputs and must not need a private
profile, real credentials, or access to Home Assistant.

Create the local environment from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Run these checks after installing the pinned development requirements:

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tooling/validate_catalog.py
.venv/bin/python tooling/sync_manager_bundle.py --check
.venv/bin/ruff check .
```

The catalog validator checks local metadata against the checked-in schema. It
does not download artifacts, prove repository trust, or install modules.

The installed App uses its separately pinned Python 3.13/Linux amd64 runtime,
not the local bootstrap interpreter. Root `schemas/` and `hahapent.json` are
canonical. After changing them, run `tooling/sync_manager_bundle.py` and commit
the resulting `manager/` copies. `--check` and the synthetic tests reject drift.
Never copy private files into the App build context.

## App image and fixture checks

Set `HAHAPENT_SOURCE_REVISION` to the reviewed published fixture-source commit,
then build the deterministic A/B artifacts:

```sh
.venv/bin/python tooling/build_fixture.py --output-dir build/fixtures \
  --revision "$HAHAPENT_SOURCE_REVISION" --release-tag test-fixtures-v1
```

The builder emits two versioned ZIPs and a separate test catalog. It accepts only
the fixture's explicit source-file allowlist and pins catalog provenance to the
supplied commit. See [integration packaging](integration-packaging.md). The
committed App test catalog uses the reviewed fixture release; fixture entries
never enter the normal catalog.

On a host with Docker, the source build command is:

```sh
docker build --platform linux/amd64 --tag hahapent-runtime:local manager
```

The `app-runtime` CI job runs `tests/runtime/image_smoke.py` and
`tests/runtime/engine_smoke.py` inside that actual image with networking disabled.
It checks imports, denial of direct/forged Ingress HTTP requests, and a synthetic
install/update/rollback/removal sequence with persisted ownership. It receives
no Supervisor or developer token. The ordinary Python 3.9/3.13 matrix remains
separate. Checkout v7.0.1 and setup-python v7.0.0 use reviewed SHA pins and Node 24;
all hosted jobs retain only `contents: read` permission.

An image build or synthetic check does not prove native HA operation. The
coordinator records actual App installation, Ingress actions, authorized Core
restarts, and the loaded fixture sensor separately in the Task 002 report.

## Live access command

```sh
.venv/bin/python tooling/check_access.py
.venv/bin/python tooling/check_access.py --ssh
```

This is a separate live operation for the coordinator, using the protected
profile's exact test-dev target and credential-file reference. It is not a CI
check. Read [access and secrets](access-and-secrets.md) and follow
[the runbook](test-dev-runbook.md) before using it. Its observed API results do
not establish every administrative capability.

`--ssh` adds read-only checks with the dedicated key and pinned host key. Only
`--file-probe` explicitly enables a unique non-executable marker round trip and
cleanup in a new project directory under the configuration mount. The flag
implies SSH; it never installs an integration or calls a device service.
An absent `custom_components` directory with a writable parent is reported as
`AVAILABLE_NOT_EXERCISED`; the read-only check does not create that directory.
Reports describe checks in that invocation; historical Git/API writes and the
backup are documented separately in the task evidence report.

## Git checkpoints

Preserve an existing repository's history, branch protections, and merge policy.
After establishing `main`, use a task branch. Stage explicit paths, inspect the
staged diff, and run synthetic checks before each push. Only the coordinator
may merge or push.

```sh
.venv/bin/python tooling/check_secrets.py --staged
.venv/bin/python tooling/check_secrets.py --history
.venv/bin/python tooling/check_secrets.py --outgoing origin/main
```

Use `--outgoing origin/main` only after the base ref exists and is the verified
remote base; use the history scan for the initial push with no remote base.
Inspect all outgoing commits, not only the working tree. CI uses
`--no-private-values` so public validation never reads local credentials.

The private-value scan supplements public pattern checks on the coordinator's
machine. Never weaken it to publish a known secret. A clean scan does not replace
manual review for household information or operational data.

After each push, independently verify the actual remote commit and the completed
CI conclusion for that commit. Queued or running CI is not a passing result.
Never force-push or rewrite shared history.

## Task 002 implementation checkpoint

At the assembled source checkpoint on 2026-09-08, the coordinator confirmed the
following results. These results describe local source validation; hosted image
and live acceptance were still pending at this checkpoint. Their final outcomes
and release identifiers are maintained in [Task 002](../tasks/002-suite-manager.md).

| Check | Result | Evidence scope |
| --- | --- | --- |
| Unit tests | `PASS` | 191 synthetic tests on Python 3.9.6; assembled coordinator run |
| Ruff | `PASS` | Assembled repository Python lint |
| Catalog validation | `PASS` | Released v1 metadata and original empty-draft compatibility |
| App bundle drift | `PASS` | Committed schemas and normal catalog match canonical root files |
| Runtime dependency hashes | `PASS` | All seven pinned Python 3.13/Linux amd64 wheels downloaded with hash verification |
| Hosted amd64 App image | `NOT_TESTED` | Pending at this local checkpoint; use the completed CI result in Task 002 |
| Live App/Ingress lifecycle | `NOT_TESTED` | Pending at this local checkpoint; coordinator-owned test-dev acceptance |
| Final Manager release | `NOT_TESTED` | Pending at this local checkpoint; source/artifact/public-download verification required |

## Task 001 verification record (historical)

Evidence updated 2026-09-08T21:47:51+02:00 (Europe/Ljubljana). The tested
implementation checkpoint and completed hosted runs are linked below. The full sanitized
access and repository report belongs in
[Task 001](../tasks/001-access-and-repository.md); private reports remain under
`~/.local/state/hahapent/`.

| Check | Result | Meaning |
| --- | --- | --- |
| Unit tests | `PASS` | 88 synthetic tests; Python 3.9.6 |
| Catalog validation | `PASS` | Empty draft catalog and schema; offline metadata only |
| Ruff | `PASS` | Repository Python lint |
| Staged/outgoing secret checks | `PASS` | Exact private values plus patterns, paths, history and messages; repeated before each push |
| Remote commit verification | `PASS` | Initial privacy checkpoint and source commit `ecbfaeb` independently matched remote heads |
| Completed CI | `PASS` | [Push run](https://github.com/djeZo888/HAHAPent/actions/runs/34270701339) and [PR run](https://github.com/djeZo888/HAHAPent/actions/runs/34270756867); Python 3.9 and 3.13 |

Use `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`,
`AVAILABLE_NOT_EXERCISED`, and `NOT_REQUIRED` as defined in
[access and secrets](access-and-secrets.md). Do not turn a read-only result into
a claim that writes, restores, restarts, or device operations were exercised.

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

## Historical Task 003 candidate verification

The Aquarius candidate is read-only: all write profiles are disabled after the
first bounded hardware test failed its reconnect/restoration window. The original
lamp values and Automatic mode were subsequently restored and confirmed. This
failure and the installed Manager's catalog delivery constraint are recorded in
[Task 003](../tasks/003-led-integration.md), separately from software tests.
Recovery was confirmed 517.0 seconds after the initial write for channel values
and 608.7 seconds for the original mode; the ten-second test limit was not met.

Coordinator verification on 2026-09-09 (Europe/Ljubljana):

- `.venv/bin/python -m unittest discover -s tests -q`: **258 PASS** on Python 3.9.6.
  Includes 51 protocol/client tests and 12 committed-source packaging tests.
- `python -m pytest tests/ha_aquarius -q --disable-socket --allow-unix-socket`:
  **38 PASS** with Python 3.14.7, HA 2026.9.1 and dependencies pinned in
  `requirements-ha-test.txt`. See [native test setup](../tests/ha_aquarius/README.md).
  Two tests use the actual client and a TCP simulator, with connections confined
  to loopback. The remaining framework fixtures disable network sockets.
- `.venv/bin/ruff check .`, `tooling/validate_catalog.py`, and
  `tooling/sync_manager_bundle.py --check`: **PASS** for the source checkpoint.
- Supplied original reference suite: **21 PASS**, offline/synthetic, separate
  from the repository suite and actual lamp evidence.
- Checkpoint `a8f7176`: remote SHA matched; [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34282588822).
  This first checkpoint contains privacy/task evidence, not the later integration.
- Candidate source `56a0b81`: exact remote SHA and
  [completed hosted CI](https://github.com/djeZo888/HAHAPent/actions/runs/34284413351)
  **PASS**, including native HA framework tests. The
  [read-only prerelease](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
  has three verified public assets; unauthenticated downloads, exact hash matching,
  empty packaged write allowlist and actual Manager archive validation **PASS**.

Tests cover query echoes, partial/coalesced/extended frames, both channel orders,
unknown modes, invalid percentages, fresh-connection post-write verification,
stale-state conflicts, no retry/replay, cancellation during socket cleanup,
coordinator queue invalidation, native reconfiguration/identity, and quiescing
before platform unload. Tests deliberately use fictional write-enabled profiles;
the packaged profile allowlist is empty. No CI accesses the private lamp or HA.

## Task 002 release-code verification

The coordinator confirmed the following results for Manager 0.1.1 and release-code
commit `81f4e2327d837409330032f505df52f1bb67fa26`. The completed
[hosted run](https://github.com/djeZo888/HAHAPent/actions/runs/34278506135)
includes the actual amd64 image. Final cleanup/restart evidence and publication
verification are maintained in [Task 002](../tasks/002-suite-manager.md); the
published release is [v0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/v0.1.1).

| Check | Result | Evidence scope |
| --- | --- | --- |
| Unit tests | `PASS` | 195 synthetic tests on Python 3.9.6; assembled coordinator run |
| Ruff | `PASS` | Assembled repository Python lint |
| Catalog validation | `PASS` | Released v1 metadata and original empty-draft compatibility |
| App bundle drift | `PASS` | Committed schemas and normal catalog match canonical root files |
| Runtime dependency hashes | `PASS` | All seven pinned Python 3.13/Linux amd64 wheels downloaded with hash verification |
| Hosted amd64 App image | `PASS` | Completed run above: image build, imports, negative HTTP authorization, engine lifecycle and persistence |
| App repository/store installation | `PASS` | 0.1.0 installed through the normal repository and App store path |
| Real Ingress and native HA lifecycle | `PASS` | Install/configure A 0.1.0, update B 0.2.0, Core-loaded version checks, rollback A, native entry removal and code uninstall |
| Configured uninstall guard | `PASS` | Code removal blocked until the native HA configuration entry was removed |
| Manager independence | `PASS` | Fixture sensor remained loaded while the Manager was stopped |
| Normal App update | `PASS` | 0.1.0 to 0.1.1 retained settings, registry and code backups |
| Graceful App stop | `PASS` | 0.1.1 reached Supervisor's clean stopped state |
| Literal developer-computer power-off | `NOT_TESTED` | No physical Mac power-off test was performed |
| Full Home Assistant restore | `NOT_TESTED` | No restore over the live environment was performed |

Uninstall removed the owned fixture code after native entry deletion. Its retained
code backup and conservative recovery restart reminder are intentional recovery
state, not an installed fixture or configuration entry. Backup readability,
post-cleanup Core/App restart checks, and the final KNX baseline are documented
in the coordinator's Task 002 report rather than inferred from these checks.

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


## Task 003 continuation

The continuation starts at merged main `7066bd6` on
`task/003-complete-aquarius`; see the current authorization and evidence in
[Task 003](../tasks/003-led-integration.md). The historical read-only artifact and
incident report are retained. New immutable Manager/module versions will carry
validated fixes.

The coordinator reran `tooling/check_access.py --ssh` (PASS), created/downloaded
and decrypted a fresh encrypted backup including Manager data (PASS), and reviewed
current startup/KNX effects (PASS). Private HA-side native TCP measurements used
only system/channel queries: ten complete reads passed in 0.322–0.520 seconds.
Temporary Python packages were fetched, signature-verified and extracted with
Alpine's [package tooling](https://wiki.alpinelinux.org/wiki/Apk); they were not
installed into the SSH App's package database. All target configuration, helper
transport and raw reports remain outside Git.

The initial continuation source checkpoint passed 304 synthetic unit tests
(57.673 seconds), 47 native HA framework tests and Ruff/catalog/bundle checks.
The later native form-serialization repair passed 14 config-flow tests and
53 total HA framework tests. These are synthetic checks; FlowManager HTTP
serialization is covered explicitly after an actual 0.1.0 setup failure exposed
the missing test boundary.

The first 26-test autonomous-worker review preceded actual direct-TCP A–E passes.
F01 then timed out during its first recovery read, abandoned the remaining
reserve and exceeded the ten-second bound. Subsequent deliberate restoration
confirmed the original channels and Automatic; the estimated total excursion
was about 53.16 seconds. That failure and the original longer incident remain
in [Task 003](../tasks/003-led-integration.md).

The repaired worker and HA-service adapter passed the superseding independent
gate:

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_validation tests.test_aquarius_ha_validation -q
.venv/bin/ruff check tooling/aquarius_validation.py tests/test_aquarius_validation.py tooling/aquarius_ha_validation.py tests/test_aquarius_ha_validation.py
```

Result: **62 tests PASS in 53.171 seconds; Ruff PASS**. The 43 base-worker tests
exercise simulated timing, native loopback TCP and detached-process cleanup;
the 19 adapter tests use synthetic services and loopback HTTP. Exact reviewed
source/test hashes and the failure cases are recorded in the
[independent review](aquarius-validation-review.md#reviewed-source-and-independent-results).
Read-only retries use at most three fresh connections and 2.5 seconds per stage,
preserving four seconds for initial restoration and two seconds before a remaining
original-mode action. Transport-only loss of a cleanup system-query reply permits
fresh full-state confirmation, never a repeated write. Unsafe or competing
replies remain terminal. Events include absolute monotonic timestamps and the
failed connection/query phase. Network loss can still prevent confirmed recovery.

Actual repaired **F02 direct-TCP validation PASS**: a one-point increase, original
channels confirmed at 2.056392 seconds, original Automatic at 2.653862 seconds,
and total excursion 2.653872 seconds. Launching SSH returned in 0.140 seconds;
the detached worker completed locally. Two later read-only checks confirmed
Automatic. Together with A–E, this supplies successful bounded evidence for all
six direct channel controls. Actual HA Number/Select service controls remain
pending and are not inferred from the adapter tests.

Actual Manager 0.1.2 App update, Ingress refresh and cache persistence passed.
Its later Refresh discovered module 0.1.1 without rebuilding the App; the real
Manager update from module 0.1.0 to 0.1.1 and gated Core health checks passed.
The repaired native HA UI reached `create_entry`, with six numeric 0–100 Numbers
and an Automatic Select. Diagnostic acceptance, rollback/removal and final
reinstallation remain pending. Module 0.1.1 is still read-only; source 0.2.0 and
actual native controls are being prepared. These delivery results do not yet
establish final owner-ready operation or Manager/development-connection independence.

# Task 002 — Initial Suite Manager

Status: **COMPLETE**. Final live verification: 2026-09-08T23:11:52+02:00
(Europe/Ljubljana). Manager **0.1.1** remains installed and running on test-dev.
Task 001 remains historical evidence. Task 003 has not begun; license selection
remains pending.

## Release and installation

[Suite Manager 0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/v0.1.1)
was published through GitHub Releases with five verified assets: the Manager
source bundle, fixture A and B ZIPs, their separate test catalog, and SHA256SUMS.
All five published assets were downloaded again without authentication and matched
their checksums. Release source: `81f4e2327d837409330032f505df52f1bb67fa26`.
[Release-code CI](https://github.com/djeZo888/HAHAPent/actions/runs/34278506135)
completed successfully, including the actual amd64 image build and runtime tests.

In HA, add `https://github.com/djeZo888/HAHAPent` under **Settings → Apps →
App store → Repositories**. Install and start **HAHAPent Suite Manager**, then
open its Ingress UI as an administrator. Keep protection mode enabled.
[Installation/recovery](../docs/installation.md), [JSON contract](../docs/catalog.md),
and the [generic integration template](../templates/integration/README.md)
are included. The normal catalog is intentionally empty until real modules exist.

## Delivered behavior

The App has no LAN management port. Each request verifies the trusted Supervisor
Ingress peer and the user's current active administrator role through the
Supervisor-provided Core credential. It maps only HA configuration, explicitly
at `/homeassistant`, and uses `/data` for settings, registry, journals and backups.
No workstation credential/profile is shipped or used inside the App.

The interface supports catalog search, version/compatibility/dependency details,
explicit extra-source trust, install/update, native HA configuration links,
rollback, and owned-code removal. Source removal/outage preserves installed
ownership. Core, HACS/manual and externally modified code cannot be taken over;
remaining native entries block uninstall. Downloads validate public HTTPS/DNS,
redirect hosts, total time/size, SHA-256 and safe ZIP contents before staged writes.
Serialized filesystem swaps use persistent journals and a registry commit point.

The unreleased draft JSON v1 was finalized without inventing v2. The original
empty draft remains readable. Settings, catalog and registry have independent
schema versions, bundled schemas, defaults, compatibility/feature gates and
preserved optional extensions. Unsupported future documents are rejected without
overwriting them. HA manifests retain HA's native format.

## Actual live acceptance

All operations below used the designated test-dev. Module mutations used the
real Ingress UI; configuration creation/deletion used HA's native UI.

| Check | Result and observation |
| --- | --- |
| Existing access | PASS — protected API/SSH checks run once; credentials, key and host pin reused |
| Repository/App-store installation | PASS — Supervisor built/installed candidate 0.1.0 from the actual repository |
| App security/mounts | PASS — protected, default AppArmor, amd64, no LAN ports/host network, only `homeassistant_api`; config writes through explicit mount |
| Normal catalog and search | PASS — empty normal catalog; separately enabled device-free catalog and searched its fixture |
| Install A | PASS — UI installed 0.1.0; files installed and not configured were reported separately |
| Native configuration | PASS — Manager link opened native form, submission created one fixture entry; loaded sensor reported 0.1.0 |
| Update B | PASS — UI installed 0.2.0, showed running 0.1.0/restart pending; after gated Core restart sensor reported 0.2.0 |
| Independent integration | PASS — fixture stayed loaded with its expected sensor value while Manager was stopped; checked with A and B |
| Normal Manager update | PASS — App-store update 0.1.0 → 0.1.1 preserved test setting, registry, installed B and rollback backup |
| Clean App stop/restart | PASS — 0.1.1 stopped as `stopped`, started/restarted normally and retained state |
| Configured uninstall guard | PASS — actual UI blocked removal until the native entry was deleted; B remained installed/loaded |
| Rollback A | PASS — UI restored 0.1.0; after gated Core restart sensor reported 0.1.0 |
| Native entry removal | PASS — direct domain page, fixture row menu → Delete; native deletion returned HTTP 200 |
| Uninstall | PASS — UI removed owned fixture code and retained its recovery backup |
| Final cleanup | PASS — no fixture config entry, sensor, code directory or temporary swap directories; test catalog disabled |
| Final App state | PASS — 0.1.1 started, protected, authenticated Ingress healthy; zero installed modules and zero normal catalog modules after final App restart |
| Live unauthorized requests | PASS — direct API and forged administrator-header mutation returned 403; Ingress without a session returned 401 |
| KNX preservation | PASS — entry loaded, connected and project present after every Core restart; startup/configuration and project file baselines unchanged |

The retained removal backup is intentional recovery state, not installed fixture
code or native configuration. Its conservative restart reminder survives App
restarts even though the operator verified the final Core restart. It requires
explicit action to restore code. Published/bundled device-free artifacts remain
separate from the normal catalog.

## Backup, restart and recovery evidence

A fresh encrypted pre-change HA configuration/database and Terminal & SSH backup
was downloaded privately. Its existing recovery key was reused and retained.
Isolated decryption and selected configuration-content readability passed using
`securetar==2026.4.1`, matching the installed Supervisor's dependency. No live
restore was performed; a full restoration rehearsal is **NOT_TESTED**.

The startup preflight found no automations, scripts, scenes, KNX entities,
exposures or time-server configuration. Core configuration validation and the
unchanged private baseline were checked before each necessary restart. KNX's
normal telemetry database/journals were excluded from immutable file comparison;
the configured project and startup files were preserved. No deliberate device
controls, standalone KNX reload, production access, HA/firmware upgrade, or
Supervisor/OS/VM restart was performed.

The browser harness initially abandoned a native setup form; HA then rejected a
duplicate as already in progress. A gated Core restart cleared that transient
flow, and the complete native setup succeeded in one session. This was not
reported as a successful configuration test until entry creation and loaded
sensor behavior were verified.

[SSH recovery procedure](../docs/test-dev-runbook.md#ssh-recovery-if-core-cannot-start)
is documented. A live failed-Core recovery and workstation power-off are
**NOT_TESTED**. Source inspection confirms the fixture has no workstation,
Manager, network, timer or device dependency; actual Manager-off operation passed.

## Repeatable tests and checkpoints

- **195 local synthetic tests PASS**, Python 3.9.6. Ruff, offline catalog validation
  and canonical App bundle drift checks PASS. Public CI also passes Python 3.13.
- Actual amd64 Docker image build, imports, real HTTP access-denial requests and
  in-image install/update/restart-instance/rollback/remove lifecycle PASS in CI.
  Public CI is synthetic and has no private HA/profile/token access.
- Synthetic coverage includes invalid/future/duplicate/deep JSON, optional
  extension preservation, source trust/identity/outage/removal, compatibility,
  dependencies, ownership conflicts, unsafe/corrupt ZIPs and manifests, public
  DNS/redirect/TLS bounds, real HTTP response parsing, slow responses, serialized
  changes, per-phase interruption, disk-full recovery, App persistence,
  administrator/CSRF failures, and graceful SIGTERM with an active transaction.
- Real public A/B downloads passed without a GitHub token and matched their
  hashes. Live validation found an HTTP response-lifetime bug; the fix and real
  parser regression were committed before deployment. Live stop validation found
  the initial exit-status problem; 0.1.1 fixed it and its clean stop was verified.
- Staged/outgoing scans compared actual private values plus forbidden patterns,
  paths and history before pushes. Release archive members and uploaded asset
  sizes/digests were checked. Credentials/backups/household details are not in Git.

Meaningful checkpoints: authorization `b453f3c`; immutable fixture source
`d98256a`; App implementation `4c2e2ba`; public-download fix `085f41c`;
0.1.1 candidate `804899d`; tested release merge `81f4e23`.
[PR 3](https://github.com/djeZo888/HAHAPent/pull/3) and
[PR 4](https://github.com/djeZo888/HAHAPent/pull/4) merged without rewriting history.
The [fixture release](https://github.com/djeZo888/HAHAPent/releases/tag/test-fixtures-v1)
remains pinned to its original source/bytes.

## Exact tested environment and limits

| Component | Version |
| --- | --- |
| HA Core / pinned Frontend | 2026.9.1 / 20260826.6 |
| Supervisor / HA OS | 2026.08.0 / 18.2 |
| Architecture / existing Terminal & SSH | amd64 / 10.4.0 |
| KNX library | xknx 3.20.0 |
| Manager | 0.1.1; normal update from candidate 0.1.0 tested |
| App base/runtime | Python 3.13.15, Debian Bookworm slim; immutable Docker digest in Dockerfile |
| Runtime validators/bridge | jsonschema 4.25.1 / websocket-client 1.9.0; hashed transitive pins |
| Browser acceptance | Chromium 140.0.7339.16 via Playwright 1.55.0 |

Only amd64 and the recorded HA release were exercised live. Future HA versions,
physical integrations, non-admin live account provisioning, live disk exhaustion,
full restore and literal Mac power-off were not exercised. Failure injection and
non-admin roles use synthetic fixtures. There is no dependency solver, automatic
update or backup pruning; removed/unconfigured-code restart indicators are
conservative. Code rollback does not undo configuration migrations or device
settings. Task 003 awaits owner details and authorization; its template contains
no LED implementation.

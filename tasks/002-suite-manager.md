# Task 002 — Initial Suite Manager

Status: authorized and in progress under the revised Task 002 assignment.
This replaces the Task 001 placeholder; Task 001 remains completed history.

## Deliverable

A working amd64 Supervisor-managed App in `manager/`, installed through the
repository/App-store path and verified through its real administrator-only
Ingress UI. No LAN management port. Built-in integrations and catalog remain in
this repository. Task 003 is not authorized; license selection remains pending.

## Acceptance

- Reuse private access, run existing read-only API/SSH checks once, and preserve
  that contract. Reconcile project instructions and runtime/restart safeguards.
- Review/update Node.js 24 action pins. Test actual runtime/image plus synthetic CI.
- Finalize unreleased JSON draft v1 with separate settings/catalog/registry schema
  versions, compatibility/feature gates, preserved extensions, bundled schemas,
  older empty-draft readability, future-version rejection and duplicate-key checks.
- Explicit source trust and repository identity; origin/version/compatibility/docs,
  offline installed entries, source changes independent from code installation.
- Bounded verified HTTPS/artifacts, safe extraction and manifest identity;
  no moving branch module releases, scripts, ownership takeover or unsafe deps.
- Serialized staged filesystem swaps, persistent ownership/journal, backups,
  update/removal rollback, interrupted/disk-full recovery; preserve unrelated data.
- Block removal until native HA config entries are removed. Distinguish code
  installation, restart pending, and configured integration state.
- Fresh encrypted backup plus isolated decryption/readability; SSH recovery plan.
  Review startup automations/KNX before necessary authorized Core restarts; stop
  restarts on a concrete unresolved physical-effect risk. No device commands.
- Actual Ingress lifecycle: list → install A → configure → update B → verify →
  rollback A → remove native config entry → uninstall. Device-free fixture only,
  outside the normal catalog. Verify operation with Manager stopped; App restart
  persistence and failures/conflicts/untrusted access using fixtures/mocks.
- Publish a real tested release with aligned artifacts/versions, completed CI,
  short installation/use/recovery docs, JSON contract and generic Task 003 template.
- Remove fixture/config entries; leave Manager installed/healthy; preserve KNX.

## Evidence

Evidence is recorded here as work completes. Private installation-specific data
stays under `~/.local/state/hahapent/`; no unexecuted check is reported as PASS.

### Candidate checkpoint

- Read-only API/SSH baseline: PASS, run once using existing protected access.
- Fresh encrypted pre-change backup: PASS; downloaded privately. Isolated
  decryption and selected configuration readability: PASS using
  `securetar==2026.4.1`, matching the installed Supervisor. Live restoration:
  NOT_TESTED; no live restore was performed.
- Startup preflight: PASS for the device-free fixture lifecycle. No startup
  automations, scripts, scenes, KNX entities, exposures or time-server
  configuration were present. Existing KNX entry loaded and connected, project
  present. Private file baselines must still match before each Core restart.
- Device-free source checkpoint: `d98256a11eff686f0a925f9a4187624e59bc0cd0`;
  [completed CI](https://github.com/djeZo888/HAHAPent/actions/runs/34274693395).
  [Immutable A/B fixture release](https://github.com/djeZo888/HAHAPent/releases/tag/test-fixtures-v1)
  published through the actual Releases API; uploaded sizes/digests verified.
  This fixture publication is not the Manager release or live acceptance.
- Local assembled candidate tests, lint, catalog and bundle checks: PASS.
  Final count and hosted App image/live acceptance results follow below.
- Live App deployment, Ingress lifecycle and Manager release: PENDING.

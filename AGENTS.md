# HAHAPent project instructions

## Current scope

Tasks 001–003 are complete. Task 003's final committed baseline is
`cbe8d2f6c9a2ec4c04564da3230cf4cae2e08a24`; Manager 0.1.2 and Aquarius Plant
LED 0.2.0 are installed and configured on protected test-dev. Its actual native
controls, lifecycle, startup and independence evidence remain historical in
`tasks/003-led-integration.md`. Preserve the working installation and all
immutable releases; do not repeat bootstrap or rebuild/redesign Suite Manager.

Task 004 authorizes improving this existing integration: clearer mode status
and Resume schedule, configurable evidence-backed channel labels, versioned
state-preserving software On/Off, native Tile sliders, immutable module
publication/update, and necessary gated test-dev Core restarts. Leave the final
version installed and configured for owner review. Current evidence belongs in
`tasks/004-aquarius-ux.md` and `docs/development.md`.

The private camera share is for read-only optical observation only. Never
publish its URL/token, device targets, frames/video or operational evidence.
Use multiple frames for optical comparisons; do not guess ambiguous colour
pairs or infer PWM frequency. A–F unique IDs must remain stable. An ambiguous
pair stays configurable and gets one grouped owner-confirmation request.

Only the coordinator performs live operations. Extend the proven detached
HA-side worker with offline failure tests and documented independent review
before new experiment types. Initial optical samples change one channel by at
most five percentage points at a modest output (initial ceiling 20%), within
ten seconds including confirmed cleanup. Hold time must retain the existing
early recovery reserve. Software shutdown is a separately authorized bounded
mode test preserving the observed starting mode. The observed Manual baseline
requires Manual-first recovery: confirm mode 1 and original output; only observed
Shutdown-zero followed by independently confirmed Manual-zero and a fresh exact
guard may admit one deliberate saved-vector restoration. A retained Off vector
followed by changed Manual output is contradictory and prohibits replay. Automatic
recovery sends only Automatic. Validate readback before enabling a shutdown profile. Never blindly overwrite
competing changes. Stop further experiments after a failure until confirmed
recovery and a repaired/reviewed procedure permit another attempt.

No setup, startup, polling, reload or reconnect path may write lamp state.
Only explicit actions may switch power or restore a saved mix. Unknown saved
origin falls back to the lamp's existing schedule on explicit On; never invent
full-brightness channel values. Keep runtime memory versioned and profile-bound.
Do not upload/edit schedules, presets, effects or clock settings; do not operate
Shelly, KNX, other devices, production, provisioning, firmware or factory reset.
Do not change network/security/camera settings or global Recorder settings.
A failing experiment does not stop safe investigation or independent task work.
Do not regenerate credentials. License selection remains pending.

## Credentials and privacy
Resolve the private profile at `~/.config/hahapent/bootstrap.json`, then its
`credential_file`; the default credential location is
`~/.config/hahapent/secrets/credentials.txt`. These paths persist across all
project tasks and worktrees. Preserve their contents; do not regenerate or
delete them during ordinary cleanup. Never copy credentials into a checkout
or worktree. Read them programmatically, never as shell code. Never
print credential values, secret-derived fingerprints, authorization headers,
raw HTTP error bodies, or sensitive configuration. Keep private files at 0600
and private directories at 0700. Public source uses generic example targets.
Keep reports/state under `~/.local/state/hahapent/` and backups under
`~/.local/share/hahapent/backups/`. No apartment coordinates, entity/user lists,
device identifiers, KNX addresses/projects/keyrings, logs, backups, or raw owner
handoff belongs in Git.

## Operational boundaries
Only the coordinator may mutate HA or merge/push Git. Subagents may implement,
test, or review isolated assigned source files; never provide them raw secrets.
Use only the exact repository and host selected by the protected profile.
Preserve KNX, existing integrations, automations, App keys/options, and remote
history. No device controls outside the authorized bounded Task 004 lamp tests, production access, network scans,
Proxmox administration, Supervisor/OS/VM restarts, or firmware upgrades.
Authorized Core restarts require the documented startup/KNX and backup safety gate.
Before deployment take a fresh encrypted backup, download it privately, retain
its recovery key and verify isolated decryption/readability where supported.
Do not restore over live HA merely as a test. Reuse Terminal & SSH unchanged.
Install HAHAPent through the actual repository/App-store path; expose no LAN
management port and enforce administrator authorization behind trusted Ingress.
App-container root is not Proxmox or HA OS host root. Never disable TLS/SSH
verification, App protection mode, or existing security protections.

## Development and checkpoints
One repository contains Manager and independently versioned built-in modules.
Optional extra sources require explicit trust and the versioned catalog contract.
Do not overwrite HACS/manual/Core-managed integrations. Preserve unrelated files
and user configuration. Installed integrations must work with Manager/Mac off.
Stage explicit files. Run synthetic local checks and staged/outgoing secret
checks before each push; verify the actual remote commit and completed CI result.
Never force-push or rewrite shared history. Use a task branch after establishing
main and preserve any existing merge policy. Do not infer tested capability from
an API permission flag or queued CI job. Report PASS, FAIL, BLOCKED, NOT_TESTED,
AVAILABLE_NOT_EXERCISED, or NOT_REQUIRED honestly.

Use `.venv/bin/python tooling/check_access.py` for read-only API checks, add
`--ssh` for read-only deployment access, or explicitly use `--file-probe` for
the authorized isolated marker round trip. Test-dev credentials are never
available to public CI. A new task must not inherit authority to mutate HA
merely from a previous task's completed write probe.

Task 004 commands and evidence are recorded in `docs/development.md` and
`tasks/004-aquarius-ux.md` as checks complete. Tasks 001–003 evidence remains historical. Public CI must use only
synthetic fixtures and minimal built-in GitHub workflow permissions.

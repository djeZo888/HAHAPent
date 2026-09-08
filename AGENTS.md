# HAHAPent project instructions

## Current scope
Tasks 001 and 002 are complete; their historical Manager 0.1.1 acceptance
evidence is in `tasks/002-suite-manager.md`. The Task 003 continuation has
installed Manager 0.1.2 on protected test-dev and verified catalog refresh/cache
persistence. Current acceptance evidence is in `tasks/003-led-integration.md`. Task 002's deployment/Core restart authorization
was specific to that completed device-free lifecycle. Future deployment,
integration or Core restart work must follow the current user's authorization
and the runbook; do not infer a blanket operational grant from prior tests.
Task 003 continuation authorizes targeted Manager catalog fixes, App builds,
updates/restarts, module publication/deployment/native configuration, and
necessary test-dev Core restarts after the runbook backup/startup/KNX gate.
Finish with a working Aquarius Plant LED installation, configured and available
for owner verification. The former no-rebuild restriction does not apply to
these targeted changes. Preserve the immutable read-only release and historical
failed-test report.
Before renewed lamp writes, repair the failed recovery path, pass offline
exception/cancellation/connection-loss tests, and document independent code review.
Use a self-contained HA-side transaction with monotonic deadlines and cleanup
independent of the development connection. Initial excursions change one channel
by at most five percentage points for at most ten seconds, including deliberate
restoration of channels and original mode, with an early measured recovery margin.
Use a private validation-only target profile until all six channels and explicit
Manual/Automatic behavior pass fresh hardware readback. A failed experiment
pauses further writes for recovery and repair, while safe investigation and
other authorized implementation work continue. Do not repeat a live experiment
while restoration is unconfirmed or overwrite competing changes blindly.
No setup, startup, polling, reconnect or reload path may write lamp state.
Private target configuration, raw captures and supplied evidence stay outside Git.
After lifecycle tests, reinstall/configure the final working version and verify
operation with Manager and the development connection stopped.
Do not regenerate credentials or repeat bootstrap. License selection is pending.

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
history. No device controls outside the bounded Task 003 lamp tests, production access, network scans,
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

Task 003 commands and evidence are recorded in `docs/development.md` and
`tasks/003-led-integration.md` as checks complete. Task 001 and Task 002 evidence remains historical. Public CI must use only
synthetic fixtures and minimal built-in GitHub workflow permissions.

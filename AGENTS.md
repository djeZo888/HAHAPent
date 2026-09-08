# HAHAPent project instructions

## Current scope
Task 001 is complete. The revised Task 002 assignment explicitly authorizes
implementing, installing, starting/stopping/restarting and testing HAHAPent
Suite Manager on the protected profile's test-dev HA, including the complete
lifecycle of a device-free test integration through the real Ingress interface.
Necessary HA Core restarts are authorized only after the startup/KNX preflight
and current encrypted backup/decryption checks in the runbook. Do not ask for
routine approval already granted by that assignment. Stop a restart if unsafe
physical effects cannot be excluded and report the concrete blocker.
Task 003 (aquarium LED integration) remains unauthorized and awaits owner details.
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
history. No intentional device controls, production access, network scans,
Proxmox administration, Supervisor/OS/VM restarts, or firmware upgrades.
Task 002 permits necessary Core restarts only after the documented safety gate.
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

Tested commands and evidence are recorded in `docs/development.md` and
`tasks/002-suite-manager.md` as checks complete. Task 001 evidence remains historical. Public CI must use only
synthetic fixtures and minimal built-in GitHub workflow permissions.

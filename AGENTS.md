# HAHAPent project instructions

## Current scope
Task 001 initializes this single repository and verifies access to the approved
test-dev environment. Do not implement the Suite Manager (Task 002) or aquarium
LED integration (Task 003). The manager folder remains a scaffold without an
installable App manifest. License selection is pending.

## Credentials and privacy
Resolve the private profile at `~/.config/hahapent/bootstrap.json`, then its
`credential_file`; the default credential location is
`~/.config/hahapent/secrets/credentials.txt`. Never copy credentials into a
checkout or worktree. Read them programmatically, never as shell code. Never
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
Proxmox administration, Core/Supervisor/OS/VM restarts, or firmware upgrades.
Take and verify a pre-change backup before authorized HA App configuration.
Only the official Terminal & SSH App may be installed/configured for Task 001.
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

Tested commands and evidence are recorded in `docs/development.md` and
`tasks/001-access-and-repository.md` as checks complete. Public CI must use only
synthetic fixtures and minimal built-in GitHub workflow permissions.

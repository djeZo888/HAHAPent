# Access and secrets

## Private bootstrap

Resolve `~/.config/hahapent/bootstrap.json` first, then the profile's
`credential_file`. The default credential location is
`~/.config/hahapent/secrets/credentials.txt`. The profile selects the only
repository and host authorized for live operations. Public examples use generic
targets; they are not a fallback destination.

Read the profile and credentials programmatically. Never source or execute a
credential file as shell code. Never copy either file into a checkout, worktree,
test fixture, CI artifact, issue, or commit. Keep private files at `0600` and
private directories at `0700`.

| Data | Location |
| --- | --- |
| Bootstrap profile and secrets | `~/.config/hahapent/` |
| Runtime reports and state | `~/.local/state/hahapent/` |
| Verified backups and recovery material | `~/.local/share/hahapent/backups/` |

These are persistent workstation paths shared by future project tasks and
worktrees. The supplied file was relocated byte-for-byte; neither checkout
cleanup nor virtual-environment recreation should remove it. Never regenerate,
rotate, relocate, or delete the stored credentials without a task requiring it.
Filesystem protection is local plaintext storage, not encryption or a vault.

Git HTTPS authentication uses a repository-local credential helper that reads
the protected file internally. The remote contains no token. Git credential
path matching is enabled and HTTP redirects are disabled. The helper accepts
only this repository and does not store additional copies. GitHub CLI and an
SSH deploy key are unnecessary for the verified HTTPS workflow. A deployment
key would not replace GitHub API permissions.

The distinct HA private key is
`~/.config/hahapent/secrets/hahapent_ha_dev_ed25519`; its public server key is
pinned in `~/.config/hahapent/ha_known_hosts`. The unattended key has no
passphrase, so its protection depends on this workstation and its permissions.
The backup recovery password is retained under the private secrets directory;
its exact filename and backup location are in the private task state.

Do not print credentials, secret-derived fingerprints, authorization headers,
raw HTTP error bodies, or sensitive configuration. Failure messages must report
the operation and sanitized status without echoing returned data. Never include
credentials in command arguments or enable shell tracing around secret handling.

## Allowed operational scope

Only the coordinator may mutate Home Assistant or merge/push Git. Subagents may
edit, test, and review assigned source files; they receive no raw secrets.

Task 001 is limited to repository bootstrap and access verification against the
approved test-dev host. If needed and authorized, the only App that may be
installed or configured is the official Terminal & SSH App, after a verified
pre-change backup. Preserve existing App keys and options. Never disable
protection mode, TLS verification, SSH host-key verification, or other existing
security protections.

Terminal & SSH sessions run inside the App container. A container-root session
is not evidence of Home Assistant OS host access or Proxmox privileges. The
official App documentation also distinguishes its web terminal from separately
configured network SSH access.
([Terminal & SSH documentation](https://github.com/home-assistant/addons/blob/master/ssh/DOCS.md))

Do not access production, scan networks, administer Proxmox, control devices,
upgrade firmware, or restart Core, Supervisor, OS, or the VM. Preserve KNX,
integrations, automations, and remote Git history.

## Public evidence

Only sanitized capability results belong in Git. Never commit apartment
coordinates, entity/user lists, device identifiers, KNX addresses, projects or
keyrings, logs, backups, or raw owner handoff documents. Ignore rules are a
convenience, not proof that a commit is safe.

Before each push, review explicitly staged files, run synthetic tests, and scan
both staged content and every outgoing commit for secrets. After pushing,
verify the actual remote commit and wait for completed CI. A permission flag,
successful authentication, or queued workflow proves only that specific fact.

Use these statuses consistently:

| Status | Meaning |
| --- | --- |
| `PASS` | The stated check ran and met its stated acceptance condition. |
| `FAIL` | The check ran and the acceptance condition was not met. |
| `BLOCKED` | A required prerequisite prevented the check or action. |
| `NOT_TESTED` | The check was not run; no capability claim is made. |
| `AVAILABLE_NOT_EXERCISED` | Availability was observed, but the action was not performed. |
| `NOT_REQUIRED` | The check or action was unnecessary for the current scope. |

Backup creation and verification do not prove restoration. A read-only API
result does not prove write access, restart permission, or safe device control.

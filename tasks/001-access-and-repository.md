# Task 001 — access and repository verification

Evidence checkpoint: 2026-09-08T21:42:41+02:00 (Europe/Ljubljana). Task 001 only.
Hosted source-check verification is pending at this checkpoint.

## Capability evidence

| Capability | State | Evidence and limit |
| --- | --- | --- |
| Credential protection | PASS | Exact supplied bytes relocated to the persistent external canonical path; 0600 files, 0700 directories; checkout copy removed; no pre-existing Git history/index |
| GitHub authenticated API | PASS | Authenticated account and exact repository verified; public visibility preserved |
| Git fetch and push | PASS | Initial main commit `bde6fc11398ddbb0c54e491de44420e469ad4736` pushed and independently matched through remote heads; actual fetch completed |
| API Contents | PASS | Created the useful Task 001 branch ref at the verified safe commit using the API |
| Issues | PASS | Created [Task 001 issue #1](https://github.com/djeZo888/HAHAPent/issues/1) |
| Repository Administration | PASS | Updated the project description; existing rules/security settings inspected and preserved |
| Pull requests | NOT_TESTED | Source checkpoint PR pending |
| Actions/workflows | NOT_TESTED | Actions enabled; completed hosted source-check run still required |
| Release API | NOT_TESTED | No product release is needed or created |
| Optional GitHub SSH deploy key | NOT_REQUIRED | Persistent scoped token-based HTTPS Git works |
| HA REST | PASS | Identified HA before credentials; authenticated `/api/` and `/api/config` |
| HA WebSocket | PASS | Authentication, `get_config`, `auth/current_user` and admin-only `config/auth/list` succeeded; user-list payload discarded |
| HA administrator role | PASS | Authenticated token has `is_admin=true`, `is_owner=true` |
| Token-to-login username binding | NOT_TESTED | Returned display name differs from supplied login; display name is not proof of username; user IDs kept out of public evidence |
| Password login | NOT_TESTED | Unnecessary for established token/key workflow; no password attempts made |
| HA App management | PASS | Supported `supervisor/api` WebSocket forwarding; pre-existing official Terminal & SSH inspected and configured |
| SSH | PASS | Dedicated key and noninteractive authentication; host key obtained through authenticated existing Ingress terminal and pinned |
| File deployment route | PASS | Writable HA configuration mount and HA CLI accessible; SSH terminates in App container |
| Marker round trip | PASS | Repeatable `--file-probe` created a unique non-executable marker, compared exact bytes, removed marker and empty directory |
| Future custom integration directory | AVAILABLE_NOT_EXERCISED | Directory absent; writable configuration parent verified. No integration package or directory was created |
| Core/Supervisor information | PASS | Both read through Supervisor and HA CLI |
| Bounded logs | PASS | Requested 30 Core log lines through CLI; content discarded, never published |
| Configuration validation | PASS | `ha core check --raw-json` completed with `result=ok`; no Core restart |
| Pre-change backup | PASS | Encrypted partial backup of HA configuration/database and Terminal & SSH completed; downloaded archive metadata verified; recovery password retained privately |
| Backup decryption / full restore | NOT_TESTED | Retained backup and key do not prove a full restore |
| Core/Supervisor/OS/VM restart | AVAILABLE_NOT_EXERCISED | Supported mechanisms identified; no disruptive lifecycle test executed |
| KNX / existing installation | PASS | No intentional device commands, KNX reload/config changes, custom integration installation, or production access; physical-device behavior was not tested |

## Verified installation

- Home Assistant Core: `2026.9.1`.
- Supervisor: `2026.08.0`, healthy and supported at inspection.
- Home Assistant OS: `18.2`; `amd64`, QEMU x86-64 virtual-machine image.
- Official Terminal & SSH: `10.4.0`, protection mode retained.
- Existing endpoint uses local HTTP; it is not encrypted. No host/router/firewall/TLS configuration changes.
- Proxmox host administration was not attempted; VM packaging does not itself
  prove which management platform operates the hypervisor.

The audited HA OS/Supervisor environment supports the planned App packaging.
The Manager remains a non-installable scaffold. Installed module behavior and
Ingress authorization for the future Manager remain Task 002 acceptance work.

## Changes and preservation

Initialized the single repository with persistent project instructions, privacy
exclusions, an empty draft v1 catalog/schema, synthetic fixtures, access tooling,
publication checks, development documentation, and hosted synthetic CI.
The license decision remains pending. Existing repository visibility was kept;
no protections were removed and no LAN CI runner or Actions secret was added.

Reused Terminal & SSH. Added only the dedicated project public key and required
LAN host-port mapping while preserving its existing options. SSH password login
remains disabled. Only this App was restarted. The encrypted backup was taken
before that change. HA Core, Supervisor, OS and the VM were not restarted.

Credentials remain at `~/.config/hahapent/secrets/credentials.txt`, with the
persistent profile at `~/.config/hahapent/bootstrap.json`. Future tasks and
worktrees read the same files; no token needs regeneration for task continuity.
Installation-specific reports, endpoint, paths and backup/key records remain
under `~/.local/state/hahapent/` and other private project directories.

## Source verification and completion gate

Local synthetic tests, Ruff, and draft catalog validation are exercised before
publication. Staged/history/outgoing scans include actual private-value
comparison locally, filenames, all committed path aliases, commit/tag messages,
and removed historical content. Public CI uses synthetic/pattern checks only.

The initial GitHub API permission flags were not treated as write evidence.
Real writes above are independent checks. Administration permission may be
removed from the token after setup if future repository administration is not
needed; no token scope has been changed automatically. Releases remain untested.

Next: complete the source checkpoint PR and hosted CI, then record the final
readiness conclusion here. No Task 002 or Task 003 implementation is authorized
by this checkpoint.

- [Task 002: initial Suite Manager](002-suite-manager.md) is next after Task 001.
- [Task 003: LED integration](003-led-integration.md) awaits owner protocol and
  function specifications and completion of Task 002.

## Version-sensitive references

The installed release was checked against
[Core 2026.9.1 current-user implementation](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/auth/__init__.py),
[admin-only user-list command](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/config/auth.py),
[Supervisor forwarding](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/hassio/websocket_api.py),
and [backup API implementation](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/components/backup/websocket.py).
The official [Terminal & SSH configuration](https://github.com/home-assistant/addons/blob/master/ssh/config.yaml)
reported the same `10.4.0` version as the installed App during this audit.

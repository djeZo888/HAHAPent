# Test-dev access runbook

This runbook covers Task 001 only. Resolve the protected profile before any live
operation and use only its selected repository and test-dev host. The coordinator
owns live mutations and Git merge/push operations. Public commands and examples
must not contain selected target values or credentials.

## 1. Check prerequisites

Confirm private profile and credential-file locations and restrictive permissions
without printing their contents. Check the working tree and preserve unrelated
files. Resolve only the explicitly selected host and service endpoints; do not
scan addresses or discover neighboring systems.

Authenticate using programmatically loaded credentials. Keep errors sanitized.
Use verified TLS where the selected URL uses HTTPS and strict SSH host-key
verification. If trust material is unavailable or a key differs, stop that
connection and obtain a trusted verification path; never bypass verification.

## 2. Establish read-only evidence

Use the access tool to test the selected Home Assistant API. The documented REST
API uses bearer authentication, but a successful request proves only the tested
endpoint and token access.
([REST API](https://developers.home-assistant.io/docs/api/rest/))

Record sanitized results for API authentication, installation type and versions,
Supervisor availability, and the required access paths. Parse responses in
memory and retain only the fields needed for the result; do not dump complete
configuration, user/entity lists, device identifiers, or logs.

Keep authentication identities separate: token ownership/admin status does not
prove a separately supplied username/password works. Likewise, Supervisor API
availability does not prove file access, SSH login, backups, or restarts.

Check the official Terminal & SSH App's installation, state, protection, Ingress,
and network SSH availability using sanitized observations. Preserve its existing
keys and options. The official documentation says that its web terminal and SSH
sessions enter the App container, and network SSH needs separate authentication
and port configuration. Treat each path as a separate capability.
([Terminal & SSH](https://github.com/home-assistant/addons/blob/master/ssh/DOCS.md))

## 3. Back up before an authorized App change

If Task 001 needs an authorized official Terminal & SSH installation or
configuration change, create the pre-change Home Assistant backup first. Verify
completion, expected scope, and availability of the backup artifact and any
required recovery material. Store local backup material only beneath
`~/.local/share/hahapent/backups/`, with private permissions. Preserve the
existing App options and keys for a narrow rollback.

Record backup creation, artifact verification, and restore testing separately.
Do not report a restore as `PASS` when only creation or download was exercised.
Home Assistant documents backup management and recovery prerequisites in its
backup guidance.
([Backup integration](https://www.home-assistant.io/integrations/backup/))

If a usable backup cannot be verified, mark the App change `BLOCKED` and retain
the current configuration.

## 4. Make the smallest authorized App change

Only the official Terminal & SSH App is in scope. Preserve existing options,
authentication behavior, and protection mode. Add only the needed authorized
access, with a dedicated key where the existing configuration permits it. The
official App's password mode and key mode are mutually exclusive; do not switch
an existing authentication mode without resolving that impact.
([Authentication options](https://github.com/home-assistant/addons/blob/master/ssh/DOCS.md))

An authorized change may require the Terminal & SSH App itself to start or
restart. It must not restart Core, Supervisor, OS, or the VM. Verify App health
and the new access path afterward. If it fails, restore only the changed App
settings/keys from the recorded prior state and recheck the original access.
Do not perform a whole-system restore as an automatic troubleshooting step.

## 5. Verify bounded capabilities

Use harmless, narrow checks for SSH login, the App-container user context, and
required filesystem access. If an explicitly authorized write/delete check is
needed, use a newly created Task 001 marker in an approved location, verify it,
and remove only that marker. Never edit existing integration or configuration
files merely to prove write access.

Do not infer host root or Proxmox privileges from App-container root. Do not
intentionally control devices, touch KNX, upgrade firmware, access production,
or restart Core, Supervisor, OS, or the VM. Log availability can be checked
without collecting or committing raw logs.

## 6. Finish the repository checkpoint

Run the synthetic commands and secret checks in
[development](development.md). Stage only intended public files. Preserve remote
history and merge policy, use a task branch after `main` exists, and never
force-push. Verify the actual remote commit and completed CI result after push.

Update [Task 001](../tasks/001-access-and-repository.md) with exact sanitized
outcomes and remaining blockers. Keep operational reports in
`~/.local/state/hahapent/`. Do not mark unexercised writes, restore operations,
restarts, or device controls as tested. Stop at the Task 001 boundary; Manager
and LED implementation are later tasks.

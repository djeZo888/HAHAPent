# Test-dev runbook — Task 002

The revised Task 002 assignment authorizes Manager deployment and the device-free
integration lifecycle on the existing test-dev. The coordinator alone performs
HA mutations and Git merges/pushes. Reuse the protected profile, credential file,
dedicated SSH key and pinned host key from Task 001. Never display or copy secrets
into source, images, the Manager, browser traces, or published artifacts.

## Access and backup gate

1. Preserve local/remote changes and work from current main on a Task 002 branch.
2. Run `.venv/bin/python tooling/check_access.py --ssh` once, read-only. Its
   contract stays unchanged; deployment uses separate tooling. Password login
   and token-to-login binding are unnecessary when token/key access works.
3. Create and download a fresh encrypted HA backup before live deployment.
   Keep it under `~/.local/share/hahapent/backups/`, recovery material under the
   private secrets directory and evidence under `~/.local/state/hahapent/`.
4. Verify completion, scope, protected archive metadata, and isolated decryption
   and content readability using supported tooling. Do not restore over live HA
   merely to prove recovery. Record any limitation separately from creation.
5. Retain SSH recovery instructions: stop the Manager if needed, restore only
   Manager-owned test code from its retained code backup, run `ha core check`,
   and use an authorized Core start/restart. Do not edit `.storage` or KNX files.
   A full-HA restoration requires a separate recovery decision.

## Required Core restart gate

Review startup automations, reachable scripts, and KNX startup/write behavior
using only the necessary configuration/metadata, kept private. Establish a
baseline for existing KNX configuration and operational state without sending
telegrams or device-service calls. If unsafe physical effects cannot be excluded,
do not restart; report the exact blocker and finish independent work.

When safe, the assignment authorizes necessary test-dev Core restarts without
another routine approval. Verify readiness, fixture behavior and KNX's previous
operational state after each restart. Preserve KNX, existing automations and
unrelated integrations. Never restart Supervisor/OS/VM, upgrade HA/firmware,
administer Proxmox, scan networks, or access production.

## Deploy and exercise the actual App

Install HAHAPent through its repository/App-store path. Retain protection mode,
minimum mounts/API permissions, and no LAN management port. Map the HA
configuration explicitly; the Manager's `/config` is not assumed equivalent to
Terminal & SSH. Use Supervisor-issued credentials inside the App, never the
workstation's owner token. Prove administrator authorization on direct APIs and
the trusted Ingress gateway boundary, not just sidebar visibility.

Through the real Ingress UI exercise: list, install fixture A, native HA
configuration, update B, verify, rollback A, remove its native config entry, and
uninstall owned code. Keep the fixture out of the ordinary catalog. Confirm the
integration remains loaded while the Manager is stopped, and preserve settings,
ownership and transactions across App restarts. Remove fixture/config entries
at the end; leave Manager installed and healthy.

Keep code rollback distinct from HA configuration migrations and device state.
Removal must refuse remaining config entries and must never modify `.storage`.

## Publication and completion

Run local synthetic checks, actual amd64 App/image tests, redacted publication
scans, and completed hosted CI. Publish actual versioned release artifacts with
aligned manifests/digests and concise install/use/recovery instructions. Do not
invent a publishing license. Retain exact versions, release/commit, lifecycle
and recovery results privately; commit sanitized evidence only. Task 003 remains
out of scope. Do not report software ready from tests or CI alone.

# Test-dev runbook — Task 002

Task 002 is complete; its recorded authorization covered Manager deployment and
the device-free lifecycle. Reuse this procedure for future work only within the
current user assignment's authorization. The coordinator alone performs
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

## SSH recovery if Core cannot start

This is an operator recovery procedure, not a live failure/restore test result.
Use the existing protected SSH profile and pinned host key; keep all logs private.
Terminal & SSH exposes HA configuration at the profile's `/homeassistant` mount.

1. Stop only Manager with `ha addons stop <manager-slug>` so it cannot mutate
   files during diagnosis. Obtain its slug from the installed App metadata.
2. Run `ha core check`. Inspect only necessary Core errors privately. Do not
   restart until startup effects and the failure cause are understood.
3. If a newly changed Manager-owned module is responsible, preserve its directory,
   registry/journal and retained backup. A coordinator can quarantine **only that
   verified owned domain** outside `custom_components` (for example, under a new
   timestamped recovery directory in the configuration mount). Never move the
   whole custom-components directory, edit `.storage`, or touch KNX.
4. Run `ha core check` again, then use the currently authorized `ha core start`
   or `ha core restart`. Verify Core and the prior KNX state. A configured entry
   whose code is quarantined may report setup failure; this does not justify
   deleting its configuration behind the native interface.
5. Reconcile the quarantined code with the retained known-good backup and ownership
   records before resuming Manager mutations. It intentionally blocks externally
   modified/missing owned files; do not bypass that guard or invent a registry.
   App data backups preserve `/data`, which is separate from the SSH App's mount.
   If recovery is uncertain, keep the evidence and use the privately retained
   encrypted HA backup under a separate restoration decision.

Task 002 verified encrypted backup decryption/readability, normal App restart,
code rollback, and unchanged KNX startup/project baselines. It did not deliberately
break Core or perform a full live restoration. KNX's telemetry SQLite database
and journal files change during normal operation and are excluded from immutable
project-file comparisons; never alter them to make a baseline test pass.

## Publication and completion

Run local synthetic checks, actual amd64 App/image tests, redacted publication
scans, and completed hosted CI. Publish actual versioned release artifacts with
aligned manifests/digests and concise install/use/recovery instructions. Do not
invent a publishing license. Retain exact versions, release/commit, lifecycle
and recovery results privately; commit sanitized evidence only. Task 003 remains
out of scope. Do not report software ready from tests or CI alone.

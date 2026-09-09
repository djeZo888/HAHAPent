# Suite Manager installation

Use Home Assistant's Supervisor-managed App store on an amd64 system running
Home Assistant 2026.9.1 or later. The task report identifies the exact tested release.
Manager updates use the normal App-store update action. The historical 0.1.0 →
0.1.1 live update preserved settings, ownership records and code backups in
`/data`. Manager 0.1.2 is installed and verified on test-dev; its built-in catalog
refresh and persistent cache passed actual Ingress and App-restart checks.
Add `https://github.com/djeZo888/HAHAPent` as an App repository, install **HAHAPent
Suite Manager**, start it, and open its Ingress interface as an administrator.
There is no LAN port, owner-token option, or developer-computer dependency.

Keep protection mode enabled. The only additional mount is Home Assistant's
configuration directory, explicitly writable at `/homeassistant`; persistent
manager state uses the App's existing `/data` volume. The only API permission is
`homeassistant_api`. The App's normal HA update mechanism updates the Manager;
individual integrations are chosen separately in its interface.

Before changing live integration code, retain a current independently readable
backup and review integration-specific startup/restart effects. Follow the
[test-dev runbook](test-dev-runbook.md) when executing this project's acceptance
tests. No physical controls are part of the device-free fixture.

Read the [App usage and recovery guide](../manager/DOCS.md),
[JSON contract](catalog.md), and [Task 002 evidence](../tasks/002-suite-manager.md).
Manager 0.1.2's **Refresh** action retrieves canonical built-in metadata securely,
with a validated persistent last-known-good cache and bundled bootstrap fallback.
Refresh updates metadata only; select each integration version and action
explicitly. Catalog source status shows freshness or refresh failure. Manager
0.1.1 requires the App update first because its refresh covers extra sources only.
See [Task 003](../tasks/003-led-integration.md) for actual release and acceptance
status; a published candidate is not proof of live control validation.
The acceptance-test catalog is separate and requires an explicit test action.

# Aquarius Plant LED installation and use

Release 0.2.0 provides six percentage channels and explicit Manual/Automatic
selection for the validated controller profile. It is installed and configured
through Manager 0.1.2 on test-dev. All six actual HA Number controls and explicit
Manual/Automatic selection passed bounded change/readback/restoration checks
with Manager stopped and the launching development connections ended. Configured
Core startup with Manager stopped also passed. The
[Task 003 report](../tasks/003-led-integration.md) records final verification
and preserves earlier failed checks.
The immutable [0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1)
prereleases are read-only versions.

To install the working release:

1. Open Suite Manager as an administrator and choose **Refresh**. Select
   **Aquarius Plant LED**, select version **0.2.0**, then choose **Install** or
   **Update**. Refresh itself never installs code or restarts HA.
2. Complete the indicated Home Assistant Core restart after the backup and
   startup-effects checks. For a new installation, open **Settings → Devices &
   services → Add integration → Aquarius Plant LED**.
3. Enter the provisioned controller's local IP address or hostname and TCP port
   **8080**. Home Assistant must reach that address; a connection from the
   development computer is unnecessary. Setup only reads controller state.
4. Open the new Aquarius device. It exposes **Channel A** through **Channel F**,
   each from **0 to 100%** in one-point steps, and **Operating mode**. Check the
   **Write support** diagnostic before using controls. Unvalidated profiles
   expose readings but reject writes explicitly.

To try a validated control, note its current percentage and the operating mode.
Open one channel's Number control and enter a value one percentage point lower,
or one point higher if the channel is already zero. Avoid sweeping the slider.
Changing a channel preserves the other five current values and deliberately
enters and saves **Manual**, pausing the stored automatic program. Wait for the
confirmed reading, then return that channel to its noted value. If the lamp was
following its program, select **Automatic program** in **Operating mode** to
resume it. Keep initial checks brief and change one channel at a time.

Choose **Manual** explicitly to retain the current output in Manual mode; choose
**Automatic program** to resume the controller's existing schedule. Automatic
operation may subsequently change percentages. These controls do not upload or
edit schedules, map A–F to calibrated colours, or provide a software power switch.
If an action fails or the state is unavailable, inspect a fresh reading before
issuing another action; a failed request does not prove that the lamp ignored it.

Setup, reconfiguration, startup, polling, reconnect and reload remain read-only.
Only explicit controls can write a validated profile. Reconfigure the address
for the same lamp to preserve its device and entity identity. To remove the
integration, first delete its native HA configuration entry, then uninstall its
owned code through Manager. Read-only update/rollback with preserved identity,
native deletion and code removal have passed on test-dev. The final 0.2.0 release
was then reinstalled and configured; actual controls and operation without
Manager or the launching development connection passed separately. Other
controller profiles and unsupported starting modes remain read-only. Optical
colour mapping, software off, schedule editing and firmware updates are not
supported. License selection remains pending.

# Reproducible App source build

Supervisor builds `manager/` as its complete Docker context. Root schemas and the
normal catalog are canonical; regenerate their committed build-context copies
with `python tooling/sync_manager_bundle.py` and verify with `--check`. CI rejects
drift. Runtime does not fetch remote schemas or read files outside its App context.

The Dockerfile uses official
`python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`.
On 2026-09-08, Docker Hub's registry returned the amd64 child manifest
`sha256:2f2e5a876c71a6757f55ec57f2add0225ddaf01c802a33fcc29073943f94d907`
with Python `3.13.15`; the explicit version tag resolved to the same child.
Dependencies and Linux amd64 wheel hashes are pinned in `manager/requirements.txt`.
The build uses no implicit `BUILD_FROM`, unpinned package, or package source build.
These pins reproduce selected inputs; they do not promise identical Docker image
metadata across different Docker builders.

Public CI builds `linux/amd64`, checks imports and security failures through the
actual HTTP server, and runs synthetic engine changes inside that image without
network access. It separately runs the bootstrap-compatible Python matrix. It
does not contain test-dev credentials or prove a live HA deployment.

References: [App configuration](https://developers.home-assistant.io/docs/apps/configuration/),
[Ingress requirements](https://developers.home-assistant.io/docs/apps/presentation/#ingress),
[official Python image](https://hub.docker.com/_/python).

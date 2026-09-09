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
See [Task 004](../tasks/004-aquarius-ux.md) for current release and acceptance
evidence, including retained failures and untested behavior.
The acceptance-test catalog is separate and requires an explicit test action.

# Aquarius Plant LED installation and use

The immutable [version 0.3.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.1)
provides six intensity controls, software On/Off, clear mode status, Resume
schedule, per-lamp labels and native Tile sliders. It fixes the saved-origin
display issue found in 0.3.0. Source and catalog CI passed, and the
[catalog update](https://github.com/djeZo888/HAHAPent/pull/12) merged. Version 0.3.1
is installed and configured on test-dev with source, entity mapping, labels and
dashboard verified. Actual Manual- and Automatic-origin power, all six Number
services, native reload, configured Core startup with Manager stopped and
read-only connection-contention recovery passed. The release and detailed
acceptance record are in [Task 004](../tasks/004-aquarius-ux.md).

To install or update:

1. Open Suite Manager as an administrator and choose **Refresh**. Select
   **Aquarius Plant LED**, version **0.3.1**, then **Install** or **Update**.
   Refresh changes metadata only. Version 0.3.0 is the superseded candidate with
   the known display issue.
   Respect the compatibility gate: this module is tested against HA 2026.9.1.
2. Complete the indicated Core restart after the backup and startup-effects
   checks. An existing installation keeps its configuration entry; do not add
   another one. Open the existing Aquarius device when the entry is loaded.
3. For a new installation, choose **Configure in HA** or **Settings → Devices &
   services → Add integration → Aquarius Plant LED**. Enter the already
   provisioned lamp's local IP address or hostname and TCP port **8080**.
   The connection originates from HA; direct development-computer access is
   unnecessary. Setup reads the controller without changing its output.
4. Confirm the device's **Write support** and power-support information. Only
   validated controller profiles permit controls. The device exposes **Lamp**,
   **Mode status**, **Resume schedule**, and six percentage Number entities;
   the existing **Operating mode** selector remains under configuration.

Use **Mode status** to distinguish **Following schedule**, **Manual override**,
and **Off**. **Resume schedule** explicitly returns to the lamp's existing stored
program; it does not upload or edit a schedule. Automatic percentages can change
over time, but stepping versus interpolation has not been established.

**Lamp Off** requests software Shutdown, leaving mains power unchanged. HA saves
the current origin first. Explicit **On** restores a trusted saved Manual mix
when Off originated from Manual, or resumes the stored schedule for an Automatic
origin. Missing, incompatible or unconfirmed memory falls back to the schedule;
it never invents full brightness. Zero percentages alone do not mean Off, and an
unreachable lamp is unavailable. If the lamp is Off, choose On or Resume schedule
before adjusting a channel.

Open the integration's **Configure** options to name the six channels. Defaults
remain **Channel A–F** until a per-lamp mapping is supplied. Choose a colour or
a distinct short custom label; `protocol_channel` always retains A–F. Options
preserve unique IDs, current entity IDs and owner-assigned entity names. A custom
HA entity name takes precedence over the selected integration label. Task 004
identified four colours on its tested lamp; D/F red versus ruby remains
unresolved and configurable, with one grouped owner question pending. Do not
apply that lamp's mapping as a universal default.

Use the [native Tile example](examples/aquarius-tile-dashboard.yaml) with the
existing entity IDs. It provides six `numeric-input` sliders, a Light toggle,
read-only mode status and a Resume schedule button. Preserve other dashboards
and views; the [migration review](aquarius-task004-dashboard-review.md) describes
replacing only an owned view's cards. Ordinary card taps do nothing; icon tap or
hold opens More info. A tap on the slider itself can change its value. Source,
schema and stored-dashboard checks passed; browser/iPhone touch remains untested.
The optional history card uses existing Recorder data. Removing that card does
not change recording, and no global Recorder settings are changed automatically.

For an initial permitted control check, note the current mode and percentage,
change one channel by one percentage point, and wait for confirmed readback.
Avoid sweeping the slider. A channel change enters and saves Manual while
preserving the other five fresh values. Restore the original value after the
check; if the original mode was Following schedule, use Resume schedule to return
to it. If an action fails or becomes unavailable, inspect a successful fresh
reading before another deliberate action. A failed request does not establish
that the lamp ignored it.

Setup, reconfiguration, startup, polling, reconnect and reload only read lamp
state; saved memory is used for output restoration only by an explicit action.
Reconfigure the address for the same lamp to preserve identity. For removal,
delete the native HA configuration entry before uninstalling owned code through
Manager. Rollback restores code, not lamp output, schedules or HA configuration.

[Task 003](../tasks/003-led-integration.md) retains actual 0.2.0 channel/mode,
update/rollback/removal, startup and Manager-independence results. Actual 0.3.0
Manual power, Resume and all six Number services also passed; its first
Automatic-origin composite failed the saved-origin display check and restored
the original Manual state. On 0.3.1, the corrected Manual-origin test passed in
**4.478065 seconds** and the Automatic-origin composite in **6.061891 seconds**,
both with Manager stopped. The latter confirmed saved Automatic origin and
native Resume/Off/On return to Automatic before deliberate exact original Manual
restoration. Three later independent reads matched after each test. Final 0.3.1
Number tests passed in **2.720–3.878 seconds**, each followed by three exact
independent reads. Native reload and configured Core startup with Manager
stopped passed, as did recovery after a bounded read-only connection hold.
Read-contention incidents and their successful query-only recovery remain in
the task report. Final checks confirmed Manager 0.1.2 running, all 15 Aquarius
entities available, the original Manual state and unchanged KNX/startup files.
Passive observation did not establish native HA wire-level no-write coverage;
lamp readbacks and synthetic framework checks are separate evidence.
The superseded [0.3.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0),
historical [0.2.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.2.0),
and read-only [0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1)
remain immutable. Schedule editing, presets/effects, clock writes and firmware
updates are not exposed. License selection remains pending.

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

# HAHAPent

HAHAPent provides a Home Assistant Suite Manager and independently versioned
integrations in one repository. The Manager is a Supervisor-managed App with
an administrator-only Ingress interface for explicitly trusted catalogs,
installation, updates, removal, and code recovery.

## Project status

| Task | Scope | Status |
| --- | --- | --- |
| [001](tasks/001-access-and-repository.md) | Access and repository bootstrap | Complete; historical evidence retained |
| [002](tasks/002-suite-manager.md) | Installable Suite Manager and safe module lifecycle | Complete at release 0.1.1; historical acceptance retained |
| [003](tasks/003-led-integration.md) | Aquarius Plant LED | Complete at 0.2.0; historical native controls/lifecycle/independence evidence retained |
| [004](tasks/004-aquarius-ux.md) | Software power, clearer modes, channel labels and Tile sliders | Functional delivery complete at 0.3.1; actual power, channels and lifecycle PASS; remaining limits recorded |

[Released Manager 0.1.2](https://github.com/djeZo888/HAHAPent/releases/tag/v0.1.2)
is installed and verified on test-dev, targets amd64 and exposes no LAN management
port. Its **Refresh** action retrieves validated built-in catalog metadata with
a persistent fallback cache. A new module version was discovered without
rebuilding the App; installation and update remain explicit actions.

The [Aquarius module](modules/aquarius_plant_led/README.md)
[version 0.3.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.1)
provides a software-power **Lamp** Light, **Following schedule** / **Manual
override** status, **Resume schedule**, and six independently labelled intensity
controls. Its [native Tile example](docs/examples/aquarius-tile-dashboard.yaml)
uses inline percentage sliders; ordinary card taps do nothing and icon/hold
opens More info. Existing A–F identities and owner-assigned names are preserved.
Unknown controller profiles remain read-only; setup and background paths only
read lamp state.

Version 0.3.1 repairs stale saved-origin attributes after Off. Its immutable
publication is complete; [catalog PR 12](https://github.com/djeZo888/HAHAPent/pull/12)
merged after passing CI. Version 0.3.1 is installed and configured on test-dev;
source, entity mapping, label options and the dashboard were verified. Actual
Manual- and Automatic-origin power tests passed with Manager stopped, exact
original Manual restoration and three later reads each. The Automatic test also
explicitly confirmed saved origin. All six native HA Number services, native
reload, configured Core startup with Manager stopped, and bounded read-only
connection-contention recovery passed on 0.3.1. Final checks found all 15 Aquarius
entities available, Manager running, the original Manual state restored and KNX
unchanged. The
superseded [0.3.0 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0)
and its failed Automatic-origin acceptance remain immutable historical evidence.
[Task 004](tasks/004-aquarius-ux.md) records acceptance, recovered read-contention
incidents, release status and completed CI evidence.

Four optical labels were established; the D/F red-versus-ruby pair remains
configurable and unresolved. Browser/iPhone touch behavior is **NOT_TESTED**,
Automatic stepping versus interpolation is undetermined, and passive native HA
wire coverage is inconclusive. Actual lamp readbacks, source/schema checks and
synthetic tests remain distinct evidence.

The historical read-only
[0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1)
module releases remain immutable. A separate device-free A/B integration supports
acceptance testing. License selection is pending.

Task 002's real Ingress fixture lifecycle exercised installation, native setup,
update, rollback, native removal, and code uninstall. The App also updated from
`0.1.0` to `0.1.1` through Home Assistant's normal store while retaining manager
state. The fixture
continued running while the Manager was stopped; see the task report for the
exact test scope and final release record.

Task 003 separately passed the Aquarius read-only update/rollback lifecycle,
preserved native entity identity during rollback, and completed native entry
deletion followed by Manager code removal. Final working controls and operation
independent of Manager/the development connection subsequently passed on the
reinstalled [0.2.0 release](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.2.0).
All six Number controls, explicit Manual/Automatic selection and configured Core
startup passed with Manager stopped. Task 004 extends that historical release
with configurable colour labels and software power; earlier failures remain in
the task reports.

Start with [installation and use](docs/installation.md) and the
[App guide](manager/DOCS.md). The task reports distinguish implemented software,
local checks, hosted CI and actual deployment/device evidence.

## Repository layout

- `manager/`: installable App, runtime, Ingress interface, and bundled contracts.
- `modules/`: independently versioned integrations, including the device-free fixture.
- `hahapent.json` and `schemas/`: canonical catalog, settings, and ownership contracts.
- `tooling/` and `tests/`: access checks, artifact builders, safety tests, and image smoke.
- `templates/integration/`: packaging template for separately authorized modules.
- `docs/`: architecture, development, access policy, decisions, and runbook.
- `tasks/`: completed evidence and future task boundaries.

Start with [development](docs/development.md), [architecture](docs/architecture.md),
and [access and secrets](docs/access-and-secrets.md). Operational work follows
[the test-dev runbook](docs/test-dev-runbook.md) and [AGENTS.md](AGENTS.md).

## Runtime principles

The Manager installs and maintains integration code. Installed integrations must
continue to work when the Manager or development Mac is off. Extra repositories
require explicit trust and the same versioned catalog contract. HAHAPent must
not take over integrations managed by Home Assistant Core, HACS, or manual
installation.

Public examples use generic targets. Credentials, private selected targets,
runtime state, backups, device details, and home configuration stay outside the
repository.

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
| [003](tasks/003-led-integration.md) | Aquarius Plant LED | Manager 0.1.2 and direct channel validation passed; final module 0.2.0 delivery and native control acceptance pending |

[Released Manager 0.1.2](https://github.com/djeZo888/HAHAPent/releases/tag/v0.1.2)
is installed and verified on test-dev, targets amd64 and exposes no LAN management
port. Its **Refresh** action retrieves validated built-in catalog metadata with
a persistent fallback cache. A new module version was discovered without
rebuilding the App; installation and update remain explicit actions.

The [Aquarius module](modules/aquarius_plant_led/README.md) 0.2.0 source provides
six A–F percentage controls and **Manual** / **Automatic program** selection for
the validated controller profile. All six channels passed bounded direct-TCP
change/readback/restoration tests after the recovery procedure was repaired.
Final 0.2.0 publication, installation and actual HA control acceptance are still
pending; [Task 003](tasks/003-led-integration.md) records that distinction and the
earlier failed tests. Other controller profiles remain read-only. Setup, startup,
polling, reconnect and reload only read lamp state.

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
independent of Manager/the development connection remain acceptance gates.

Start with [installation and use](docs/installation.md) and the
[App guide](manager/DOCS.md). The [Task 002 report](tasks/002-suite-manager.md)
distinguishes implemented software, local checks, hosted image checks, and live
deployment evidence.

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

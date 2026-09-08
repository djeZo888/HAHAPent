# HAHAPent

HAHAPent provides a Home Assistant Suite Manager and independently versioned
integrations in one repository. The Manager is a Supervisor-managed App with
an administrator-only Ingress interface for explicitly trusted catalogs,
installation, updates, removal, and code recovery.

## Project status

| Task | Scope | Status |
| --- | --- | --- |
| [001](tasks/001-access-and-repository.md) | Access and repository bootstrap | Complete; historical evidence retained |
| [002](tasks/002-suite-manager.md) | Installable Suite Manager and safe module lifecycle | Implementation present; acceptance and release results in the task report |
| [003](tasks/003-led-integration.md) | Aquarius Plant Plus60 / AMled integration | Not started; separate authorization and owner details required |

The initial Manager is version `0.1.0`, targets amd64, and exposes no LAN management
port. The normal catalog remains empty; a separate device-free A/B integration
supports acceptance testing. License selection is pending.

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

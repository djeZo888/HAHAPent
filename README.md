# HAHAPent

HAHAPent is a planned Home Assistant suite with a Manager and independently
installable modules in one repository. Task 001 establishes repository tooling
and checks access to the approved test-dev environment. It does not deliver an
installable Manager or a device integration.

## Project status

| Task | Scope | Status |
| --- | --- | --- |
| [001](tasks/001-access-and-repository.md) | Access and repository bootstrap | See the evidence report |
| [002](tasks/002-suite-manager.md) | Installable Suite Manager and safe module lifecycle | Planned; not implemented |
| [003](tasks/003-led-integration.md) | Aquarius Plant Plus60 / AMled integration | Planned; owner protocol and function details required |

The `manager/` directory is a scaffold. It has no installable Home Assistant App
manifest. No module is released or available for installation. License selection
is pending; no license has been chosen by this bootstrap.

## Repository layout

- `manager/`: future Manager application.
- `modules/`: future built-in modules, each with its own version and release.
- `hahapent.json` and `schemas/`: catalog and its versioned contract.
- `tooling/` and `tests/`: bootstrap validation and synthetic local checks.
- `docs/`: architecture, development, access policy, decisions, and runbook.
- `tasks/`: completed evidence and future task boundaries.

Start with [development](docs/development.md), [architecture](docs/architecture.md),
and [access and secrets](docs/access-and-secrets.md). Operational work follows
[the test-dev runbook](docs/test-dev-runbook.md) and [AGENTS.md](AGENTS.md).

## Runtime principles

The planned Manager installs and maintains modules. Installed integrations must
continue to work when the Manager or development Mac is off. Extra repositories
require explicit trust and the same versioned catalog contract. HAHAPent must
not take over integrations managed by Home Assistant Core, HACS, or manual
installation.

Public source contains generic examples only. Credentials, selected targets,
runtime state, backups, device details, and home configuration stay outside the
repository.

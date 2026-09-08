# Roadmap

Task boundaries are sequential. Completing access checks does not authorize
Manager deployment or device controls.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository scaffold, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Report actual results and unresolved prerequisites |
| [002: Suite Manager](../tasks/002-suite-manager.md) | Installable Manager with catalog and safe module lifecycle | Task 001 reviewed; installation path and restart/recovery constraints confirmed |
| [003: LED integration](../tasks/003-led-integration.md) | Aquarius Plant Plus60 / AMled module | Owner protocol/function information and separate implementation authorization |

The Manager remains a scaffold throughout Task 001. Task 002 uses device-free
fixtures for lifecycle verification and must preserve all existing integrations
and automations. Task 003 must begin with an evidence-based protocol and function
scope; this repository assumes no existing driver, packet capture, firmware,
credential, or hardware test result.

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

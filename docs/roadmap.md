# Roadmap

Task boundaries are sequential. Task 001 is complete and the revised Task 002
assignment authorizes the Manager implementation and approved test-dev lifecycle.
Task 003 and physical device controls require separate authorization.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository bootstrap, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Complete; preserve its historical report |
| [002: Suite Manager](../tasks/002-suite-manager.md) | Implemented App, trusted catalogs, owned code lifecycle, recovery, and device-free fixture | Complete hosted image tests and real Ingress acceptance, preserve restart/recovery safeguards, publish verified release |
| [003: LED integration](../tasks/003-led-integration.md) | Aquarius Plant Plus60 / AMled module | Owner protocol/function information and separate implementation authorization |

The Manager's source and packaging are implemented. Task 002 acceptance covers
install A, native configuration, update B, rollback A, native removal, and code
uninstall through the actual Ingress interface, including independence while the
Manager is stopped. Its current execution and release results are recorded in the
task report. Existing integrations and automations must be preserved throughout.

Task 003 must begin with an evidence-based protocol and function
scope; this repository assumes no existing driver, packet capture, firmware,
credential, or hardware test result.

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

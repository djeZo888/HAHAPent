# Roadmap

Task boundaries are sequential. Tasks 001 and 002 are complete, including the
published Manager release and cleaned test-dev lifecycle.
Task 003 began under the owner's revision-2 assignment. Its initial bounded
control test failed; the original lamp state was restored and further writes stopped.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository bootstrap, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Complete; preserve its historical report |
| [002: Suite Manager](../tasks/002-suite-manager.md) | App 0.1.1, trusted catalogs, owned code lifecycle, recovery, and device-free fixture | Complete; release 0.1.1 published, Manager healthy and installed fixture cleaned |
| [003: LED integration](../tasks/003-led-integration.md) | Aquarius Plant LED read-only candidate | Safe bounded control validation and authorized installed-catalog delivery remain blocked |

Task 002 exercised install A, native configuration, update B, rollback A, native
removal, and code uninstall through the actual Ingress interface. It also verified
that the fixture remains loaded while the Manager is stopped and that the normal
App update preserves state. The 0.1.1 shutdown fix reaches Supervisor's clean
stopped state. Final cleanup, restart, and release results are maintained in the
task report. Existing integrations and automations remain outside module ownership.

Task 003 has published independently packaged read-only code and synthetic
protocol/native HA tests. Actual lamp reads pass, but the first write test failed
its reconnect/restoration bound. No controller write profile is enabled. Manager
0.1.1 embeds its catalog; delivering the new built-in entry to that installed App
requires an authorized packaging update or a supported remote refresh capability.
Live module setup, update/rollback/removal and independence acceptance remain untested.

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

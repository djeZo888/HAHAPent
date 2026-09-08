# Roadmap

Task boundaries are sequential. Tasks 001 and 002 are complete, including the
published Manager release and cleaned test-dev lifecycle.
Task 003 began under the owner's revision-2 assignment. Its initial bounded
control test failed; the original lamp state was restored and further writes stopped.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository bootstrap, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Complete; preserve its historical report |
| [002: Suite Manager](../tasks/002-suite-manager.md) | App 0.1.1, trusted catalogs, owned code lifecycle, recovery, and device-free fixture | Complete; release 0.1.1 published, Manager healthy and installed fixture cleaned |
| [003: LED integration](../tasks/003-led-integration.md) | Working Aquarius Plant LED installation | Manager 0.1.2 and bounded direct channel validation passed; final 0.2.0 publication, native controls and independence acceptance pending |

Task 002 exercised install A, native configuration, update B, rollback A, native
removal, and code uninstall through the actual Ingress interface. It also verified
that the fixture remains loaded while the Manager is stopped and that the normal
App update preserves state. The 0.1.1 shutdown fix reaches Supervisor's clean
stopped state. Final cleanup, restart, and release results are maintained in the
task report. Existing integrations and automations remain outside module ownership.

Task 003 delivered Manager 0.1.2 through the App store and verified canonical
catalog refresh, persistence across App restart, and later module discovery
without another Manager image build. Actual read-only Aquarius native setup,
update, rollback with preserved identity, native deletion and code removal passed.

The original bounded lamp test and the first Channel F recovery both exceeded
the ten-second limit; those failures remain in the task record. After the
recovery worker was repaired and independently reviewed, F02 passed in 2.653872
seconds. Together with A–E, all six channels now have successful direct-TCP
change/readback/restoration evidence. The repaired worker and HA-service adapter
passed 62 offline tests; adapter tests do not establish actual HA control.

Module 0.2.0 source enables six A–F percentage controls and explicit Manual /
Automatic-program selection for the validated controller profile. Other profiles
remain read-only, as do setup, startup, polling, reconnect and reload. Final
artifact publication/CI, actual installed 0.2.0 Number/Select controls, operation
with Manager and the development connection stopped, and owner-ready acceptance
remain pending. The historical read-only releases remain immutable:
[0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1).

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

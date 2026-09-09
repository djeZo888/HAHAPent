# Roadmap

Task boundaries are sequential. Tasks 001 and 002 are complete, including the
published Manager release and cleaned test-dev lifecycle.
Task 003 began under the owner's revision-2 assignment. Its initial bounded
control test failed; the original lamp state was restored and further writes stopped.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository bootstrap, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Complete; preserve its historical report |
| [002: Suite Manager](../tasks/002-suite-manager.md) | App 0.1.1, trusted catalogs, owned code lifecycle, recovery, and device-free fixture | Complete; release 0.1.1 published, Manager healthy and installed fixture cleaned |
| [003: LED integration](../tasks/003-led-integration.md) | Working Aquarius Plant LED installation | Release 0.2.0 installed/configured; native A–F, Manual/Automatic, lifecycle and independence PASS; complete; owner verification available |

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
change/readback/restoration evidence. The initial repair passed 62 offline tests.
The first native HA attempt later returned uncertain HTTP completion; an adapter
repair released its TCP observer before delegating to HA. That reviewed repair
passed 65 combined base/adapter tests before renewed native checks. These
synthetic results do not themselves establish actual HA control.

Published module 0.2.0 is installed and configured through Manager 0.1.2. Each
actual HA A–F Number control passed a one-point change, independent changed-state
readback, and restoration of channels and Automatic mode in 3.299–4.463 seconds.
Explicit HA Manual-to-Automatic selection passed in 3.086 seconds. Two subsequent
fresh TCP checks confirmed Automatic after every test. These are actual native
HA service results, separate from the earlier direct-TCP and synthetic tests.

Manager remained stopped throughout all seven controls, while detached HA-side
workers completed after their launching SSH sessions returned in 0.149–0.179
seconds. Configured Core startup with Manager stopped also passed. Final health,
dashboard and CI verification are tracked in the task report; the working
installation remains available for owner verification.

Only the validated controller profile permits Manual/Automatic controls. Other
profiles and unsupported starting modes remain read-only; setup, startup,
polling, reconnect and reload issue queries only. Optical colour mapping and
software off remain unsupported. The historical read-only releases and earlier
failed native/transport tests remain in the evidence record:
[0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1).

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

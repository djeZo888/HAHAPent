# Roadmap

Tasks 001–003 are complete. Task 004's functional 0.3.1 delivery is complete,
installed and configured, with source, entity mapping, labels and dashboard
verified. Actual Manual- and Automatic-origin power, all six Number services,
reload, configured startup and read-only connection recovery passed. The task
report records release/CI status, historical failures and remaining evidence
limits.

| Task | Deliverable | Gate |
| --- | --- | --- |
| [001: access and repository](../tasks/001-access-and-repository.md) | Safe repository bootstrap, synthetic checks, sanitized access evidence, verified Git/CI checkpoints | Complete; preserve its historical report |
| [002: Suite Manager](../tasks/002-suite-manager.md) | App 0.1.1, trusted catalogs, owned code lifecycle, recovery, and device-free fixture | Complete; release 0.1.1 published, Manager healthy and installed fixture cleaned |
| [003: LED integration](../tasks/003-led-integration.md) | Working Aquarius Plant LED installation | Complete at 0.2.0; historical native A–F, Manual/Automatic, lifecycle and independence PASS |
| [004: Aquarius UX](../tasks/004-aquarius-ux.md) | Software power, mode status, Resume schedule, per-lamp labels and native Tile sliders | Functional delivery complete at 0.3.1; actual power, channels and lifecycle PASS; remaining limits recorded |

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
seconds. Together with A–E, all six channels then had successful direct-TCP
change/readback/restoration evidence. The initial repair passed 62 offline tests.
The first native HA attempt later returned uncertain HTTP completion; an adapter
repair released its TCP observer before delegating to HA. That reviewed repair
passed 65 combined base/adapter tests before renewed native checks. These
synthetic results do not themselves establish actual HA control.

At Task 003 completion, module 0.2.0 was installed and configured through Manager
0.1.2. Each actual HA A–F Number control passed a one-point change, independent changed-state
readback, and restoration of channels and Automatic mode in 3.299–4.463 seconds.
Explicit HA Manual-to-Automatic selection passed in 3.086 seconds. Two subsequent
fresh TCP checks confirmed Automatic after every test. These are actual native
HA service results, separate from the earlier direct-TCP and synthetic tests.

Manager remained stopped throughout all seven controls, while detached HA-side
workers completed after their launching SSH sessions returned in 0.149–0.179
seconds. Configured Core startup with Manager stopped also passed. Its final
health, dashboard and CI verification remain in the historical task report.

Only the validated controller profile permits Manual/Automatic controls. Other
profiles and unsupported starting modes remain read-only; setup, startup,
polling, reconnect and reload issue queries only. Task 003 did not provide colour
labels or software power; Task 004 adds these features with separate validation.
The historical read-only releases and earlier failed native/transport tests
remain in the evidence record:
[0.1.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0)
and [0.1.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1).

Task 004's [version 0.3.1](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.1)
was published from source `e709fc49fc8e62087ab23786707f765b9c2099dd` after
[source CI passed](https://github.com/djeZo888/HAHAPent/actions/runs/34346201803).
The [catalog PR](https://github.com/djeZo888/HAHAPent/pull/12) merged at
`0847d53e0f5bbdef25fe0ddb5ad06a65d07bd6bb`; its
[CI 34346835194](https://github.com/djeZo888/HAHAPent/actions/runs/34346835194) and
[CI 34346843859](https://github.com/djeZo888/HAHAPent/actions/runs/34346843859) passed.
[Main CI 34347190699](https://github.com/djeZo888/HAHAPent/actions/runs/34347190699)
also passed after the merge.
Actual installed 0.3.1 Manual power passed in **4.478065 seconds**. The corrected
Automatic composite passed in **6.061891 seconds**, confirming the saved origin,
native Resume/Off/On, and exact original Manual recovery. Each test ran with
Manager stopped and was followed by three exact independent reads. All six
0.3.1 Number services then passed bounded changes and restoration in
**2.720–3.878 seconds**, each with three exact subsequent reads. Native reload
and configured Core startup with Manager stopped passed with source, identities,
options and dashboard preserved. A read-only connection hold produced actual
unavailability after **5.093193 seconds**; bounded release and query-only recovery
returned the exact unchanged Manual state. Post-startup read contention also
recovered through queries only; that incident remains in the task report.
Final checks found Manager 0.1.2 running, Core running, all 15 Aquarius entities
available, the original Manual state and unchanged KNX/startup files. The
superseded immutable
[0.3.0 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0)
is retained with its known saved-origin display defect and failed Auto01 result.
That failure restored the exact original Manual state; later success must not
erase it.

The new UX provides an ON/OFF-only Light, read-only **Mode status**, **Resume
schedule**, configurable channel labels and six native Tile sliders. Explicit
On restores trusted Manual-origin memory or resumes the existing schedule;
missing origin falls back to the schedule. Background operations never restore
output. Native 0.3.0 Manual power, Resume, all six Number services, configured
startup/reload and connection-contention recovery remain historical passes;
the current 0.3.1 results are recorded separately above. See
[installation and use](installation.md) and the
[Tile example](examples/aquarius-tile-dashboard.yaml).

Four optical labels were established on the tested lamp. The D/F red-versus-ruby
pair remains explicitly configurable pending the single grouped owner question;
no global mapping is inferred. Browser/iPhone touch behavior remains unverified.
Automatic stepping versus interpolation is undetermined, and native HA wire-level
no-write coverage remains inconclusive; actual pre/post lamp state and synthetic
framework evidence are reported separately.

Schedule upload/editing, presets, effects, clock writes, firmware updates and
calibrated spectral output remain outside the current implementation.

License selection remains pending. Optional third-party sources require an
explicit trust decision and the shared versioned catalog contract.

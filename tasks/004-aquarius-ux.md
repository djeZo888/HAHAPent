# Task 004 — Aquarius Plant LED UX, optical labels and software power

Status: **IN PROGRESS**. This improves the existing integration and its installed
configuration. The owner supplied the private assignment and camera share;
neither the original attachment nor private target/capture data belongs in Git.

## Baseline and scope

Task 003 completed at main `cbe8d2f6c9a2ec4c04564da3230cf4cae2e08a24`.
Its final main CI [completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34293970401).
The new branch is `task/004-aquarius-ux`. Protected API and pinned SSH access
passed read-only checks; current HA is 2026.9.1. Existing Manager 0.1.2 and module
0.2.0 are the working baseline. Historical Task 003 failures, successful tests,
and immutable releases are retained.

Required delivery: Following schedule / Manual override status and Resume
schedule; six stable channel identities with configurable evidence-backed labels;
an ON/OFF-only native Light with versioned origin/manual-mix memory; native Tile
sliders that avoid ordinary More-info navigation; immutable module update,
actual lamp/lifecycle acceptance, and final configured owner demonstration.
Shutdown support stays separately gated until bounded hardware readback passes.
Unknown restoration origin on explicit On resumes the existing stored schedule;
no full-brightness vector is invented. Startup and background paths never write.

## Initial safety and evidence plan

- Reuse the detached HA-side worker's monotonic deadlines and guarded cleanup.
  Optical sampling begins at one-channel deltas no greater than five points,
  selected output at most 20%, and at most ten seconds including restoration.
- Compare multiple private camera frames; report ambiguous whites/reds as
  configurable pairs, never as guessed mappings. Do not infer PWM frequency.
- Preserve the observed starting mode in shutdown validation. The current stable
  Manual baseline requires Manual-first recovery. Only observed Shutdown-zero
  followed by confirmed Manual-zero and a fresh exact guard may admit one
  deliberate saved-vector restoration. Retained Off output followed by changed
  Manual output is contradictory and prohibits replay. Automatic-origin recovery
  sends only Automatic. Each path requires offline tests and independent review.
- Read-only observation may characterize normal schedule progression; no
  schedule/preset/effect/clock upload or editing is authorized.
- Use the existing backup/startup/KNX gate before deployment/Core restart.
  Preserve entry/entity identities, other dashboards, global Recorder settings,
  KNX, other devices, camera configuration, network/security and production.

## Current checks

| Check | Status | Evidence |
| --- | --- | --- |
| Completed committed baseline | PASS | Main and completed CI verified |
| Protected HA/SSH access | PASS | Existing token/key/host pin reused; no write probe |
| Native computer/iPhone surface discovery | BLOCKED currently | Computer Use reports the Mac locked; unlock requested while safe work continues |
| Private camera read-only access | PASS | Guest-scoped stream decoded; multiple frames show the LED board; no camera settings changed |
| Optical colour mapping | PASS with one ambiguous pair | Six isolated 5% samples, exact restoration after each; four colour labels established and two red channels left configurable |
| Direct Manual-origin software Shutdown | PASS | Mode 8 readback all-zero; Manual-first guarded saved-vector restoration and three later reads match original state; 2.746025 s |
| Camera software-Off observation | PASS | Multiple private frames show darkness and restored lighting; no camera settings changed |
| Native HA Manual power and Resume schedule | PASS | Manager stopped; HTTP completion, fresh TCP confirmation, exact original Manual restoration and three later reads |
| Native HA Automatic-origin power return | NOT_TESTED | Separate bounded composite under offline review |

The initial Task 004 checkpoint `beda55630fbcf743a26affccb73838cf15d15902`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34338192756).
A fresh encrypted backup was downloaded privately; isolated decryption and
selected configuration readability passed. A full live restore was not tested.
Current installed baseline retains one configuration entry/device and twelve
available entities. Actual read-only samples show stable Manual output, which
is preserved; they do not establish Automatic interpolation. The camera viewing
path now works through guest-scoped MQTT/WebRTC streaming with TLS verification.
No camera configuration was changed.

## Actual direct Shutdown evidence

The reviewed direct-worker checkpoint `072670dd49127628344caf5467ba6730474d0767`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34339505146).
The first launch was rejected during setup because the private report path was
relative. No worker transaction or lamp command began. The coordinator corrected
the launcher to use absolute paths and passed an HA-side configuration/report
check with zero lamp network operations; reviewed worker bytes were unchanged.

The following Manual-origin test passed its experiment and recovery in
**2.746025 seconds**. The lamp reported Shutdown with all six exposed channels
zero. Manual alone still reported zero, so the worker used the independently
reviewed fresh-zero guard and one deliberate original-vector-plus-Manual restore.
The final exact Manual mode/vector matched the baseline. Three later independent
read-only samples confirmed the same state. Multiple camera frames showed actual
darkness and return of the prior lighting. This is actual device/optical evidence,
separate from offline tests, and admits only the exact validated raw power profile.
Automatic-origin power, versioned HA memory and native service acceptance remain
pending. Current lamp percentages and all captures remain private.

The existing native entry was temporarily disabled through HA during direct TCP
experiments to release its polling connection. Its identity/configuration were
preserved; the final installation must be re-enabled and configured. No Core
restart, other integration change or network/security change was needed for this
pause. The earlier detached read-only observer completed before testing.

## Immutable UX candidate and native acceptance gate

Source checkpoint `bbb4b5385944ac9bd98f25086f9e0de62bcb1692` passed
[completed CI](https://github.com/djeZo888/HAHAPent/actions/runs/34340988349).
The immutable [0.3.0 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0)
was published from that exact source. Public unauthenticated downloads matched
all locally built assets, and Manager archive validation passed. The ZIP SHA-256
is `02973dfe98d440e999769c6c550f5ae53e95765b6d02ff8b31d4c47ab8071fac`.
Existing releases are retained. Actual updated-module acceptance remains pending.

The native HA service worker passed 29 independent synthetic/loopback tests,
including unknown HTTP completion and exclusive TCP handling. Its frozen hashes
and operational conditions are in the
[native acceptance review](../docs/aquarius-task004-ha-validation-review.md).
These are separate from actual native HA/lamp tests.

## Automatic power acceptance procedure decision

The observed owner baseline is Manual. Task 004 requires actual return to a
prior Automatic schedule state, so a composite acceptance test must enter
Automatic explicitly, test Off/On, then restore the original Manual snapshot.
The coordinator selected a separate twenty-second maximum, six-second
experiment and 19.5-second cleanup deadline for this composite, reserving
13.5 seconds for deliberate recovery. The task requires bounded testing without
a numerical duration for this mode/power composite. The earlier ten-second
optical and single-action native limits remain unchanged. This new procedure
requires its own offline tests and independent review before actual use.
Unknown HA completion is not cancellation and cannot authorize replay.

## Actual installed 0.3.0 and optical acceptance

[PR 11](https://github.com/djeZo888/HAHAPent/pull/11) merged the catalog candidate
at `287e74704b3c0e8cdefee993c92d3e058d7c9232`;
[main CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34342495767).
Actual authenticated Manager Ingress API refresh discovered 0.3.0 alongside all
three earlier releases. Its owned-module update passed. A gated Core restart
passed configuration validation and subsequent Core/KNX health and preservation
checks. Manager was not rebuilt. The existing Aquarius entry was re-enabled;
one entry/device, all twelve existing entity IDs, and fifteen available native
entities were verified. Installed executable source matched the release source.
The Light exposes only the ON/OFF colour mode.

Ordinary small optical increments were restored successfully, but the existing
white output obscured colour distinctions. The separately reviewed isolated
procedure passed all six actual samples at 5%, with an at-most 0.3-second hold:

| Protocol channel | Complete excursion, seconds | Later exact readbacks |
| --- | ---: | ---: |
| A | 3.933889 | 3 PASS |
| B | 3.603012 | 3 PASS |
| C | 3.710087 | 3 PASS |
| D | 3.627185 | 3 PASS |
| E | 3.637144 | 3 PASS |
| F | 3.785932 | 3 PASS |

Each test confirmed Shutdown-zero, Manual-zero, its selected isolated vector,
and deliberate exact original Manual restoration. Comparison of several private
frames and 13–15-frame sample averages established daylight white, warm white,
green and blue. The two red outputs could not reliably be assigned red versus
ruby red; one grouped owner-confirmation request was made. Per-lamp options
keep that pair explicitly configurable, without a guessed spectral mapping.
No camera settings or lamp schedule were changed, and no PWM frequency is inferred.

Native options-flow acceptance verified versioned label storage, unchanged
entry/data version and unchanged entry/device/entity IDs. An initial immediate
disk check ran before HA's asynchronous storage flush; subsequent independent
readback confirmed persistence. All detailed options and camera evidence remain
private. The native dashboard save preserved unrelated views and metadata;
independent storage readback confirmed nine Tiles, six numeric-input sliders,
ordinary tap disabled, and More info on icon/hold. Browser/iPhone touch remains
NOT_TESTED: Computer Use reported a locked Mac and unavailable browser surface.
Native API/schema/source checks do not substitute for actual touch evidence.

With Manager stopped, native Manual-origin Off/On passed in **4.409660 seconds**.
HTTP completion and fresh independent lamp readback verified Shutdown-zero and
return of the exact original Manual mix. Three later read-only samples matched.
The native Resume schedule button passed in **2.456649 seconds**, confirming
Automatic before deliberate exact original Manual restoration and three later
matching reads. This verifies explicit schedule resume without uploading or
changing the stored program. Normal Automatic stepping versus interpolation
remains undetermined from the current short observation.

All six native Number controls then passed with Manager stopped, using one-point
changes and deliberate restoration. Complete excursions were A **2.718304 s**,
B **2.923904 s**, C **2.865327 s**, D **2.885916 s**, E **2.984422 s**, and
F **3.027578 s**. Every action had known HTTP completion and three subsequent
exact original-state readbacks. These are actual native service/lamp results;
no slider touch or browser gesture is inferred from them. Detached launches
returned promptly while HA-side workers retained cleanup ownership.

## Lifecycle, recovery and Automatic acceptance incident

Actual native reload and a second gated Core restart passed with Manager
stopped. All existing identities, per-lamp label options and the owned dashboard
survived; the installed 0.3.0 source matched its immutable revision. Three fresh
readbacks confirmed exact unchanged Manual state after startup.

The passive observer operated with its narrow filter and recorded three complete
query-only diagnostic sessions with zero reported drops. Their timings exactly
matched the later diagnostic helper, while native HA traffic was absent from
the SSH App's visible namespace. Native HA wire coverage is therefore
**INCONCLUSIVE**, despite the observer's scoped `QUERY_ONLY_OBSERVED` result.
No broader capture or network/security change was attempted. The actual unchanged
state observations and source/framework no-write tests remain separate evidence.

A reviewed, detached read-only connection holder exercised actual exclusive
connection contention. HA's query failed after **5.022785 seconds**, and the
channel entities became unavailable. The holder closed within its nine-second
maximum without sending any control frame. After the native refresh cooldown,
HA recovered availability; three subsequent independent reads matched the
original Manual state. This is actual connection contention/recovery, not an
induced network outage. No lamp write service was invoked.

The first Automatic-origin composite **FAILED** at its native saved-origin
observation after successful Resume and Off. The worker did **not** send On.
Deliberate guarded cleanup restored the exact original Manual state in
**5.551953 seconds**, followed by three matching independent reads. The failure
and full private report are preserved. Further lamp writes paused for repair.
Source investigation found that Off publishes entity data before confirming its
persisted origin; the Light's cached `on_behavior` can therefore still describe
the missing-origin fallback. A native framework reproduction and separately
versioned repair are in progress. The saved-origin acceptance gate is retained;
the published 0.3.0 tag/assets will remain immutable.

The stale-state mechanism was reproduced through actual HA REST service and
state views with a synthetic TCP lamp for both origins. Candidate **0.3.1**
settles power memory before publishing the corresponding entity data; matching
channel/mode/On paths now publish after memory invalidation. Failed persistence
still publishes known physical readback, and cancellation retains the existing
unavailable handling. No protocol/client/store or frozen worker changed.
Author full native suite: **117 PASS**. Independent affected power/coordinator
suite: **56 PASS**. Packaging: **12 PASS**; Ruff PASS. The
[publication-order review](../docs/aquarius-power-publication-review.md) records
exact hashes and failure/cancellation coverage. Corrected actual lamp acceptance
remains pending publication and deployment of the new immutable version.

A second fresh encrypted backup passed isolated decryption/readability, retaining
the initial backup and its private record. Actual Manager rollback to **0.2.0**
passed. After its gated Core restart, immutable source comparison, one loaded
entry/device, all twelve original entity IDs, versioned options and the owned
dashboard were preserved. Three independent reads confirmed unchanged Manual
state. The new UX entities are unavailable while the historical version is
loaded; the final corrected version will replace it before handoff.

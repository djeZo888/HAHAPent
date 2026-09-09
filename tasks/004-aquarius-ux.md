# Task 004 — Aquarius Plant LED UX, optical labels and software power

Status: **DELIVERED for owner review**. Immutable **0.3.1** is installed and
configured on test-dev; Manager **0.1.2** is running. Actual Manual/Automatic
power, all six channel controls, rollback/update, reload, startup and read-only
connection recovery passed. The existing identities, per-lamp labels and native
Tile dashboard are preserved, and the original Manual lamp state is restored.

Browser/iPhone gestures remain **NOT_TESTED** because the Mac stayed locked and
no browser surface was available. D/F red versus ruby remains explicitly
configurable, and normal Automatic interpolation is **UNDETERMINED**. These
observational limits are not represented as passed acceptance. Private targets,
the camera share, captures and detailed operational evidence remain outside Git.

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

## Final checks

| Check | Status | Evidence |
| --- | --- | --- |
| Committed baseline and protected access | PASS | Task 003 final main/CI verified; existing token and pinned SSH reused |
| Immutable 0.3.1 publication and discovery | PASS | Exact source, public downloads, archive validation, actual Manager Refresh/Update; all earlier releases retained |
| Synthetic and HA framework checks | PASS | 117 native framework tests with synthetic lamp data; 56 overlapping independent affected tests; 12 packaging tests; completed CI |
| Camera read-only observation | PASS | Multiple frames and averages; no camera settings changed |
| Optical labels | PASS for four; D/F unresolved | Six isolated 5% samples restored exactly; ambiguous red pair configurable, one grouped owner question |
| Direct software Shutdown | PASS | Mode 8 and six zeros, optical darkness, exact Manual restoration and three later reads |
| Native Manual power on 0.3.1 | PASS | 4.478065 s; known HTTP completion and three exact restoration reads |
| Native Automatic power and Resume on 0.3.1 | PASS | 6.061891 s; saved Automatic origin, return to Automatic, deliberate original Manual restoration and three later reads |
| Earlier Automatic01 on 0.3.0 | FAIL, preserved | Stale saved-origin display stopped On; exact original Manual recovery confirmed; repaired in 0.3.1 |
| All six native Number controls on 0.3.1 | PASS | One-point changes with confirmed restoration and three later reads each; Manager stopped |
| Rollback and final update | PASS | Actual 0.3.0 → 0.2.0 → 0.3.1 through Manager; same entry/device/entity IDs, labels and dashboard |
| Native reload and Core startup on 0.3.1 | PASS | Manager stopped; source/configuration preserved and original state confirmed |
| Actual read-only contention/recovery | PASS | Unavailable state, bounded holder closure, restored availability and unchanged lamp reads |
| No unsolicited output writes | PASS in source/framework; actual state unchanged | Background paths covered by synthetic command assertions; actual lifecycle readbacks match. Native HA wire coverage is INCONCLUSIVE |
| Native Tile dashboard | PASS for schema/save/durability | Nine Tiles, six sliders, ordinary tap disabled, icon/hold More info; existing dashboard metadata preserved |
| Browser/iPhone gestures | NOT_TESTED | Locked Mac; browser surface unavailable. API/service checks are not touch evidence |
| Automatic steps versus interpolation | UNDETERMINED | Short actual samples and manufacturer manual do not establish normal firmware progression |
| Final installation and environment | PASS | Manager started, Core running, fifteen native entities available; KNX/project/startup files preserved |
| Encrypted backup | PASS for decryption/readability | Two private backups retained; full live restore NOT_TESTED |

The initial Task 004 checkpoint `beda55630fbcf743a26affccb73838cf15d15902`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34338192756).
A fresh encrypted backup was downloaded privately; isolated decryption and
selected configuration readability passed. A full live restore was not tested.
At that initial checkpoint, the installed baseline retained one configuration
entry/device and twelve available entities. Read-only samples showed stable
Manual output; they did not establish Automatic interpolation. The camera viewing
path worked through guest-scoped MQTT/WebRTC streaming with TLS verification.
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
At that checkpoint, Automatic-origin power, versioned HA memory and native
service acceptance were still pending. Lamp percentages and all captures remain
private.

The existing native entry was temporarily disabled through HA during direct TCP
experiments to release its polling connection. Its identity/configuration were
preserved, and the entry was subsequently re-enabled for native 0.3.0 acceptance.
No Core restart, other integration change or network/security change was needed
for this temporary pause. The earlier detached read-only observer completed
before testing.

## Immutable UX candidate and native acceptance gate

Source checkpoint `bbb4b5385944ac9bd98f25086f9e0de62bcb1692` passed
[completed CI](https://github.com/djeZo888/HAHAPent/actions/runs/34340988349).
The immutable [0.3.0 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0)
was published from that exact source. Public unauthenticated downloads matched
all locally built assets, and Manager archive validation passed. The ZIP SHA-256
is `02973dfe98d440e999769c6c550f5ae53e95765b6d02ff8b31d4c47ab8071fac`.
Existing releases are retained. Actual updated-module acceptance was still
pending at that publication checkpoint; the later results and incident follow.

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
Source investigation found that 0.3.0 published Off entity data before confirming its
persisted origin; the Light's cached `on_behavior` could therefore still describe
the missing-origin fallback. A native framework reproduction and separately
versioned repair then followed. The saved-origin acceptance gate is retained;
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
exact hashes and failure/cancellation coverage. At that repair checkpoint, corrected actual lamp acceptance still required
publication and deployment; the later successful results are recorded below.

Repair source `e709fc49` passed
[source CI 34346201803](https://github.com/djeZo888/HAHAPent/actions/runs/34346201803).
The immutable [0.3.1 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.1)
was published from that exact source. All three public unauthenticated asset
downloads matched the local build, and Manager archive validation passed. ZIP
SHA-256: `285b8e1d050d7679243c3d3e8a7840fdbb1e5d451327e91cb7dd883112a025d5`.
Catalog checkpoint `075752cec84bfff5b7c480459c908ed720476768` adds this version
and marks 0.3.0 superseded without changing its immutable tag or assets.
Actual corrected installation and power acceptance were separate subsequent gates.

A second fresh encrypted backup passed isolated decryption/readability, retaining
the initial backup and its private record. Actual Manager rollback to **0.2.0**
passed. After its gated Core restart, immutable source comparison, one loaded
entry/device, all twelve original entity IDs, versioned options and the owned
dashboard were preserved. Three independent reads confirmed unchanged Manual
state. The new UX entities were temporarily unavailable while the historical version
was loaded; the corrected version subsequently replaced it before handoff.

## Schedule progression evidence limit

The [official Aqua Medic app manual, English pages 14–15](https://www.aqua-medic.de/en/download/App-Steuerung-aquarius-plant-plus~d4963#page=14)
describes per-channel time points and point-by-point Demo playback. It does not
specify normal Automatic interpolation or its update cadence. Demo semantics
are not evidence for normal Automatic behavior. The brief actual Automatic
checks establish mode selection; the fixed Manual samples cannot determine
whether this firmware steps or interpolates. That behavior remains **UNDETERMINED**.
No schedule was uploaded or overwritten to manufacture a transition.

## Corrected 0.3.1 actual acceptance

[PR 12](https://github.com/djeZo888/HAHAPent/pull/12) merged at
`0847d53e0f5bbdef25fe0ddb5ad06a65d07bd6bb` after catalog checkpoint CI
[34346835194](https://github.com/djeZo888/HAHAPent/actions/runs/34346835194)
and [34346843859](https://github.com/djeZo888/HAHAPent/actions/runs/34346843859)
completed successfully. Actual Manager Refresh discovered all five preserved
module versions; its owned update installed 0.3.1. The gated Core restart passed
configuration and subsequent health checks. Installed executable source matched
`e709fc49fc8e62087ab23786707f765b9c2099dd`. The existing entry/device, twelve
original entity IDs, fifteen native entities, per-lamp options and dashboard
were preserved. Three post-update reads confirmed the original Manual state.
Manager was then stopped for corrected native acceptance.

Manual02 **PASS, 4.478065 seconds**: native Off confirmed Shutdown-zero and native
On restored the saved original Manual mix. Automatic02 **PASS, 6.061891 seconds**:
native Resume selected Automatic, native Off confirmed Shutdown-zero, the strict
Light saved-Automatic-origin check passed, and native On returned to Automatic.
Guarded cleanup then restored the original Manual snapshot. Both tests had known
HTTP completion and three subsequent exact original-state readbacks. The frozen
Automatic worker and its origin check were not weakened. Auto01 remains FAIL.

All six Number services also passed again on the corrected version with Manager
stopped. Complete excursions were A **2.720228 s**, B **3.877626 s**,
C **2.939223 s**, D **2.778980 s**, E **2.898352 s**, and F **2.747333 s**.
Each one-point change had known HTTP completion, confirmed restoration and three
later exact reads. These are actual native HA/lamp tests, separate from the
117 native-framework tests with a synthetic lamp and the overlapping 56-test
independent review run. They do not establish browser or iPhone gestures.

## Final lifecycle and handoff

The merged catalog's [main CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34347190699).
Actual 0.3.1 read-only contention produced an unavailable state after a
**5.093193-second** query failure. The reviewed holder closed within its bound;
after the query cooldown, native availability recovered and three independent
reads matched the original state. No output service was called. Native reload
then passed with three unchanged-state reads. A final gated Core restart with
Manager stopped retained the immutable source, configuration, identities, label
options and dashboard, while Core and KNX health checks passed.

The first final-startup diagnostic series had one `AquariusError` followed by
two exact matching reads. A subsequent availability check observed unavailable
entities. This is consistent with exclusive-client contention; the root cause
was not inferred as proven. A native query-only refresh recovered availability,
then a separate three-read series matched the original Manual state. The initial
failed diagnostic and failed availability check remain private evidence; they
are not relabelled PASS. No output command or rollback was used for recovery.

Final verification found Manager **0.1.2 started**, Core **RUNNING**, one loaded
Aquarius entry/device, all **15** native entities available, unchanged original
identities, and the preserved labels and nine-Tile dashboard. Startup files,
KNX project files and Manager settings matched the protected baselines. The
owner's original Manual lamp state is restored. No worker retains a lamp or
camera session. No Manager rebuild, schedule upload, other-device control,
production access or network/security/camera change was performed.

The 0.3.1 release was promoted by changing metadata only; its source tag and all
asset IDs and hashes are preserved. The embedded artifact catalog remains the
immutable publication-time candidate snapshot; the current canonical catalog
records completed actual acceptance. Earlier releases, including failed 0.3.0,
remain intact. The final source/docs checkpoint must complete CI before merge;
the final merge and CI are recorded in the Git history and owner handoff.

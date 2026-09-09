# Task 003 — Aquarius Plant LED

Status: **COMPLETE — Manager 0.1.2 and Aquarius Plant LED 0.2.0 installed,
configured and available for owner verification; all required native controls PASS**.
This task follows the owner's revision-2 assignment;
the original package, device configuration and packet evidence are private.

## Current continuation scope

The owner's continuation resumes merged main
`7066bd6425321766372607c738f6d69b941481ab` (PR #6) on
`task/003-complete-aquarius`. The private continuation supersedes conflicting
no-Manager-rebuild and indefinite write-freeze wording below. Targeted built-in
remote catalog refresh, App build/update/restart, integration deployment/native
configuration and necessary gated test-dev Core restarts are authorized.
Completion requires working installed controls, all six channels and explicit
Manual/Automatic validation, lifecycle acceptance and final owner-ready setup.

Renewed lamp controls require offline recovery/failure tests and documented
independent review first. A detached HA-side worker must own local monotonic
budgets and guarded cleanup, reserve recovery time within the ten-second bound,
and avoid blindly restoring over competing changes. A failed experiment pauses
writes for recovery/repair; independent safe work continues. The old read-only
release remains immutable. Historical evidence below records the previous
assignment and is not a current authorization restriction.

## Continuation investigation and deployment gates

- **PASS:** current protected API/SSH access; no repeated bootstrap or provisioning.
- **PASS:** fresh encrypted backup includes HA configuration/database, Terminal &
  SSH and Manager data. Download and isolated decryption/readability verified;
  live restore is NOT_TESTED. Recovery key and all archives remain private.
- **PASS:** current startup review found no automations/scripts/scenes or KNX
  entity/expose/time-server writers. Existing KNX entry is loaded; immutable
  configuration/project baseline retained privately for restart comparisons.
- **PASS, read-only hardware:** ten native HA-side TCP refreshes using the actual
  client returned a stable Automatic-mode baseline. Each complete system/channel
  pair took 0.322–0.520 seconds, including the 200 ms query separation; TCP
  connection time was 0.002–0.113 seconds. No write command was sent.
- **PASS, synthetic process check:** a detached HA-side Python process continued
  after its launching SSH session returned in 0.13 seconds. The temporary runtime
  uses signature-verified Alpine packages extracted into a private temporary
  directory; no package database, App options, protection or SSH configuration
  was changed.

The historical harness ran its decision logic on the workstation, terminated
its netcat subprocess after a 250 ms close allowance, and did not perform
restoration in the exception/finally path. These are established harness defects.
The response timeout after writing and the first failed mode-restoration sequence
do not establish a firmware incompatibility. Native TCP read-only measurements
separate connection setup cost from the old SSH/netcat adapter; post-write
processing still needs reviewed, bounded validation. No new lamp write has yet
been executed at this investigation checkpoint. Subsequent reviewed recovery
procedures and actual bounded results are recorded below.

## Manager 0.1.2 source checkpoint

Built-in Refresh now securely fetches canonical repository metadata, validates
identity/schema/features, and atomically persists a bounded cache before use.
Startup revalidates the cache against bundled identity, with a bundled fallback.
Failures retain usable metadata and show source freshness/errors; refreshing
never installs code or restarts HA. Existing extra-source and ownership gates
are unchanged. Independent review caught a cache-envelope depth-limit issue;
full-envelope validation and a regression test corrected it before release.

Coordinator checks: **108 Manager tests PASS**, including ten new catalog/cache
cases; Manager/affected-test Ruff, catalog validation and bundle checks **PASS**.
These are synthetic source checks; actual App update and cache persistence
results are recorded below.
The authorization checkpoint `5ee5cf3` matched its remote SHA and
[completed CI successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34287526405).

## Continuation live delivery and recovery evidence

Manager source `4e27a86` and PR #7 both completed CI successfully; merge main is
`56057402ccf87bdddfbc1d6e66eddd6578d01807`.
[Manager 0.1.2](https://github.com/djeZo888/HAHAPent/releases/tag/v0.1.2)
was published and updated through the actual App-store path. Actual administrator
Ingress Refresh fetched canonical metadata without installing code. Settings
and records were preserved; a normal App restart retained the validated cache
and successful-refresh timestamp. Protection and API/network permissions remain
unchanged. Read-only module 0.1.0 was then installed through the actual Manager
UI. The gated Core restart passed configuration checks and returned with Core
running, KNX loaded/connected and unchanged startup/project baselines. Native
module configuration and remaining lifecycle actions were pending at that
checkpoint; subsequent 0.1.1 native setup results are recorded below.

The [independent recovery review](../docs/aquarius-validation-review.md) and
26 offline worker tests preceded renewed controls. The exact reviewed worker
ran detached inside the SSH App's isolated Python runtime; launching SSH sessions
returned in 0.13–0.15 seconds. These are actual native TCP tests, separate from
Home Assistant entity-service tests and optical observations.

| Channel | Single-channel delta | Experiment | Original channels and Automatic restored | Excursion |
| --- | ---: | --- | --- | ---: |
| A | +1 point | PASS | PASS | 2.511 s |
| B | -1 point | PASS | PASS | 2.598 s |
| C | -1 point | PASS | PASS | 2.462 s |
| D | +1 point | PASS | PASS | 2.519 s |
| E | +1 point | PASS | PASS | 2.318 s |
| F01 | +1 point | PASS | FAIL within bound; later deliberate recovery PASS | about 53.16 s total |
| F02, repaired worker | +1 point | PASS | PASS | 2.653872 s |

Each A–E test independently read the exact changed vector and Manual mode,
restored and confirmed all original channels, then separately restored and
confirmed Automatic. Subsequent read-only checks passed. Positive one-point
changes were used where the current channel did not permit a reduction.

F01's changed state was confirmed at 0.716 seconds. Its first fresh recovery guard
read timed out after 0.8 seconds, and the worker ended at 1.518 seconds without
using the remaining recovery reserve. The sequence stopped; a separate guarded
recovery required current state to match the known test change, restored the
original channels and Automatic, and confirmed both. That recovery transaction
took 1.887 seconds. Total excursion is estimated at 53.16 seconds using HA-side
report modification times plus the initial excursion timing; it is approximate,
not a monotonic cross-process measurement. Two subsequent read-only checks
confirmed Automatic. This remains a second failed bounded test; F02 does not
change its outcome or the original incident below.

The immediate defect is abandoning cleanup after a single transient recovery
read failure. Whether the timeout occurred at connection setup or queried reply
is not established by that report. Repair requires bounded read-only retries
while reserving command/recovery time; no write retry, stale replay, or larger
ten-second allowance is authorized. Experiments remained paused until the repair
passed the offline tests and independent review recorded next.

## Repaired recovery gate and Channel F02

The [superseding independent review](../docs/aquarius-validation-review.md)
passed **62 offline tests in 53.171 seconds**: 43 base-worker tests and 19
HA-service-adapter tests, with Ruff PASS. These use synthetic state, loopback TCP
and loopback HTTP; they do not establish actual HA service control. The reviewed
source hashes are:

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| `tests/test_aquarius_validation.py` | `a6849fd273cbdbca548ffde331e4af356ee7083ca06b6e916d416d5bf73d4b61` |
| `tooling/aquarius_ha_validation.py` | `4550805ee0c45a3777eb59019c4bf539e01bf75f41974e461359f7d3f3271c37` |
| `tests/test_aquarius_ha_validation.py` | `63472b0e3c0ad6ac747b94d10bdcd958ac8af26d9692a5d3a626fb3318cacf57` |

Recovery status reads now permit at most three fresh connections within a shared
2.5-second stage budget. The existing 9.5-second cleanup deadline retains four
seconds after the initial guard and two seconds before any remaining original-mode
command. A lost cleanup system-query reply may be confirmed through fresh full
state reads; no write is resent. Partial, malformed, contradictory, changed-profile
or competing state remains terminal. Events record absolute monotonic timestamps
and failed connect/query phases. Persistent transport loss still reports
unconfirmed recovery; the timer cannot guarantee physical restoration.

The coordinator then ran the repaired worker for actual direct-TCP **F02 PASS**,
with a one-point increase. Original channels were confirmed at **2.056392 seconds**
and original Automatic mode at **2.653862 seconds**; total reported excursion was
**2.653872 seconds**. The launching SSH session returned after **0.140 seconds**,
while the detached HA-side worker owned cleanup. Two subsequent read-only checks
confirmed Automatic. Together with the earlier A–E passes, all six channels now
have successful bounded direct-TCP change/readback/restoration evidence.
This establishes no optical colour mapping. Native HA Number/Select service
validation was still pending at this checkpoint; its later actual results are
recorded below.

The interim 0.1.1 module source adds response-backed write-connection lifetime,
strict echo quarantine, fresh-socket confirmation, current Automatic vector
preservation and a three-second admitted-action deadline covering debounce and
lock queues. This interim version keeps all profiles read-only. At its initial
source checkpoint, local synthetic checks passed **304 unit tests**, **47 native
HA framework tests**, and Ruff/catalog/bundle validation.

## Native setup serialization repair

Actual native HA setup for the unchanged 0.1.0 artifact returned HTTP 500 before
showing the controller form. Private Core diagnostics identified HA's inability
to serialize the `_normalize_host` callable inside the form schema. Direct
FlowManager tests had not exercised the HTTP response serializer.

The 0.1.1 source exposes a declarative string field and performs
normalization/validation after submission, retaining normalized duplicate checks
and a clear `invalid_host` field error. Six regression cases use HA's actual
`FlowManagerIndexView._prepare_result_json` for initial/reconfigure forms and
invalid-host responses. **14 config-flow tests PASS; 53 total native HA tests
PASS; Ruff PASS.** These are synthetic framework checks. The original 0.1.0
release remains unchanged. Actual delivery and native UI evidence follow.

## Read-only lifecycle artifact 0.1.1

Source `7a640b3df6e47056554f19254493fac6fdfcdfdc` fixes the native form and
[completed hosted CI](https://github.com/djeZo888/HAHAPent/actions/runs/34289891050).
[Immutable 0.1.1 prerelease](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.1)
contains the deterministic native ZIP, catalog snapshot and SHA256SUMS.
ZIP SHA-256 is `079e4c037c68ff7ea8d67c1d6011f49bab2aaa59c85576ec4d903a58a2536588`.
All three assets were downloaded without credentials and matched their published
bytes; actual Manager archive validation and private-value scans passed. Its
shipped write allowlist is empty. This is an intermediate read-only lifecycle
version, not Task 003 completion or the final owner-ready control release.

Actual Manager 0.1.2 Ingress Refresh discovered this new 0.1.1 module version
without an App rebuild. Updating the installed module from 0.1.0 to 0.1.1 through
Manager passed, followed by the gated Core restart and health checks. Actual
native HA UI configuration reached `create_entry`; the installed entry exposes
six numeric A–F Number entities with range 0–100 and a Select reporting Automatic.
The subsequent read-only rollback preserved native device/entity identity.
Native entry deletion and Manager code removal also passed. The empty write
allowlist makes these read-only lifecycle results. Final 0.2.0 installation and
the first native control attempt are recorded below.

## Module 0.2.0 publication and installed checkpoint

The immutable
[0.2.0 release](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.2.0)
was published with three verified assets: native ZIP, catalog snapshot and
SHA256SUMS. ZIP SHA-256 is
`9658f034c69fc3cbb5743759920d4f91e4a6429491ed286ee158e4f6e8562382`.
PR #9 merged as `0f94c1c329c48b6641ac7d49204fa41a7e4bf796`;
[CI run 34291947584](https://github.com/djeZo888/HAHAPent/actions/runs/34291947584)
and [CI run 34291923648](https://github.com/djeZo888/HAHAPent/actions/runs/34291923648)
completed successfully. These publication and CI checks do not establish actual
native HA control acceptance.

Actual Manager 0.1.2 Ingress Refresh discovered 0.2.0 without another App rebuild,
and the real UI installation reached **Complete**. The gated Core restart
returned healthy HA 2026.9.1 with KNX unchanged. Native HA configuration reached
`create_entry`, producing one device, six Number entities and one Select. The
coordinator verified the entry/entity mapping to the exact protected target;
all installed Python files and the manifest matched the published source bytes.
The profile is write-enabled in this version, but that fact alone is not a
successful control test.

Manager was stopped for the independence test phase. Configured startup
availability with Manager off has separately **PASS** evidence: a subsequent
gated Core restart left HA
2026.9.1 running, the 0.2.0 entry loaded, six Numbers and the Select available,
and KNX loaded/connected with unchanged project and startup baselines. The exact
protected target and all installed Python/manifest bytes were checked again.
Two fresh post-startup TCP reads confirmed Automatic. This proves configured
startup and availability without Manager. Actual control evidence is separate:
the first attempt failed as described next, followed by repair and seven passes.

## Native HA A01 failure and read-only diagnosis

The first native HA channel test, **A01, is FAIL**. Its HTTP operation reached
unknown completion at **3.001782 seconds**. A fresh independent guard confirmed
the exact original channel vector and Automatic mode at **3.598169 seconds**.
The worker ended with an honest FAIL at **3.598303 seconds** because the HA
action's completion was unknown. Observing original output does not prove that
the HA action succeeded, was ignored or was cancelled. No PASS is claimed for
A01. Two subsequent fresh read-only checks confirmed Automatic; private
HA logs recorded admitted-action deadline errors.

Read-only diagnosis then tested connection contention. The first connection
successfully read Automatic state. With that connection still open, a second
connection timed out after **0.803462 seconds**. After releasing the first
connection, a fresh full read passed in **0.425227 seconds**, matching the exact
unchanged baseline and Automatic mode. The HA-service adapter had retained its
baseline TCP connection while invoking HA, preventing the HA client's independent
connection from completing under these observed conditions.

Further control experiments were paused. The adapter was repaired to release
its baseline connection before invoking the HA actuator, including mode cleanup.
Exclusive-connection simulation coverage and renewed independent review preceded
another live test. This was an adapter connection-lifetime defect, not evidence that the
direct-TCP channel protocol is incompatible. No larger test allowance, automatic
write retry or relaxation of unknown-completion handling is authorized.

## Final adapter gate and actual native HA controls

The [superseding adapter review](../docs/aquarius-validation-review.md#ha-observer-handoff-repair-review)
passed **22 adapter tests in 18.913 seconds**, independently, with Ruff PASS.
The combined base/adapter suite passed **65 tests in 60.676 seconds**. Three added
regressions model an exclusive TCP connection and require the observer to close
before a separate service actuator connects. The unchanged base worker retains
its bounded fresh-read recovery; no integration runtime change was required.
The reviewed adapter SHA-256 is
`7669e3c363cd1c9a38b39cd54d3dd89c3047a787a10e27c585e72a4bd686045b`;
its test SHA-256 is
`358356dc9f64e4177014e4efc2b357bee9f446d566ea0ef10d0163c934d0d685`.
The earlier assembled release-source checkpoint passed **343 unit tests** and
**56 native HA framework tests**. These remain synthetic results.

Worker-fix commit `0b2db56637f6ceab8cd74d0a2c213cdb93d0f065` was pushed;
[CI run 34292965170](https://github.com/djeZo888/HAHAPent/actions/runs/34292965170)
failed only the platform-specific EOF/reset assertion. The final checkpoint
below records its narrow repair; the earlier release-source and PR #9 CI passes
remain separate evidence.

Installed and configured module **0.2.0** then passed all seven actual native HA
tests below. **Manager 0.1.2 remained stopped throughout.** Launching SSH sessions
returned in **0.149–0.179 seconds**, before the detached HA-side workers completed
the controls and their guarded cleanup.

| Actual native HA test | Control and independent readback | Original state / Automatic confirmed | Total excursion |
| --- | --- | --- | ---: |
| Channel A02 | PASS | PASS | 3.298624 s |
| Channel B01 | PASS | PASS | 3.473584 s |
| Channel C01 | PASS | PASS | 3.526991 s |
| Channel D01 | PASS | PASS | 3.587826 s |
| Channel E01 | PASS | PASS | 4.462599 s |
| Channel F01, native | PASS | PASS | 3.520784 s |
| Explicit Manual → Automatic through HA Select | PASS | PASS | 3.086147 s |

Each channel request recorded **HTTP_COMPLETED** and a fresh independent TCP
read of the exact one-percentage-point change, with all five other channels
preserved and Manual confirmed. The worker deliberately restored and confirmed
the original channels and Automatic within ten seconds. The separate Select test
confirmed both explicit Manual and Automatic through actual HA services. Two
subsequent fresh read-only checks confirmed Automatic after every test.

Channel E also exercised a real recovery fault: its channel-restoration read
timed out after 0.8 seconds, then one fresh read-only retry confirmed recovery.
No write was repeated. Its complete 4.462599-second excursion remained within
the original bound. This is actual fault-path evidence, separate from simulation.

Together, these results demonstrate actual installed Number/Select operation
with Manager stopped and without an attached development SSH session owning
cleanup. The configured Core-startup test with Manager stopped also passed.
Literal physical power-off of the development computer was not performed.
The earlier native A01 unknown-completion FAIL, direct F01 failed recovery and
original first-test incident remain failures; none is overwritten by these passes.

Functional control acceptance, final post-test health and dashboard handoff
are **PASS**. The final task-branch head must pass its GitHub checks before
completion is merged into main. Optical colour naming/calibration is **NOT_TESTED**; software
off and program uploads are unsupported and were not exercised. No other-device
control, production access, network/security change or KNX modification occurred.

## Historical revision-2 baseline and authorization

Task 002 is complete at main commit `3ce396c27296e33473dbbbeebe68bff034d8203d`.
The fetched remote matched the clean checkout; the final
[CI run](https://github.com/djeZo888/HAHAPent/actions/runs/34280044358)
completed successfully. The private completion record agrees, and no Task 002
operator process was active. Work began on `task/003-aquarius-plant-led`.
Manager 0.1.1 is the existing completed implementation, not a new deliverable.

The owner authorizes HA-side read-only protocol diagnostics, independently
versioned module implementation/publication, the actual Manager/native HA
lifecycle, and bounded reversible tests of the selected lamp. Initial tests may
change one channel by at most five percentage points for at most ten seconds,
followed by deliberate restoration. Unexpected changes or a competing controller
stop writes. Core restarts require a fresh encrypted, privately downloaded and
readable backup plus the startup/KNX safety gate. Other devices, provisioning,
network policy, infrastructure and production remain outside scope.

## Historical revision-2 evidence

| Check | Result | Scope |
| --- | --- | --- |
| Package integrity/private placement | PASS | Supplied checksums verified; installation settings outside Git |
| Protected API/SSH access | PASS | Existing profile, credentials, key and host pin reused; no write probe |
| Supplied reference tests | PASS | 21 offline/synthetic methods, including loopback TCP; not lamp evidence |
| HA-side protocol reads | PASS | Meaningful system reply and six valid percentages; no lamp writes |
| Initial SSH forwarding attempt | FAIL | Connection reset; forwarding ended without SSH configuration changes |
| Supplied probe against channel response | FAIL | Probe required E2 FC, while the queried lamp returned E2 FA |
| Adapted read-only probe | PASS | Existing HA-side netcat transport; two queries, explicit E2 FA acceptance |
| Initial bounded channel test | FAIL | One-point Channel A change reached Manual; immediate reconnect verification failed and restoration exceeded ten seconds |
| Deliberate restoration | PASS | Fresh state matched the commanded change; all original channel values and Automatic mode were subsequently restored and read back |
| Further lamp controls | BLOCKED | Stopped after unexpected behavior; no public write-enabled controller profiles |
| Native HA on protected test-dev | NOT_TESTED | Candidate not installed; real HA framework tests use synthetic fixtures |
| Actual Manager installation/lifecycle | BLOCKED | Installed App cannot load a new built-in catalog without an App update |
| Encrypted deployment backup / Core restart | NOT_REQUIRED | No HA deployment or Core restart occurred |
| Optical colour mapping | NOT_TESTED | A–F retained; no inferred wavelength mapping |
| Repository synthetic suite | PASS | 258 tests on Python 3.9.6, including 51 protocol/client and 12 packaging tests |
| Native HA framework suite | PASS | 38 tests on Python 3.14.7 / HA 2026.9.1, including two actual-client loopback cases |
| Current test-dev health | PASS | Core running, KNX entries loaded, Manager 0.1.1 started and protected; no deployment/restart |

The supplied app-static evidence establishes raw TCP frame constructors and
the controller-specific C/D permutation. It does not establish firmware behavior.
Actual readback identified controller bytes `(28, 30)`, raw version bytes
`(26, 29)`, and channel-count byte `6`; the documented swapped controller flag
does not match. These are raw fields, not an invented firmware name or stable
hardware serial. Raw frames and actual settings remain private.

## Historical catalog-delivery constraint

Manager 0.1.1 reads its built-in catalog from the installed App's bundled file.
Its refresh action downloads extra-source metadata, but does not download the
built-in catalog. Adding the same repository as an extra source fails the
source-identity guard. Publishing the new root catalog alone therefore cannot
make this module appear in the installed Manager. Rebuilding the Manager is
excluded by this assignment. Do not bypass ownership, directly copy acceptance
code, edit App internals, or weaken source identity to conceal this constraint.
The smallest exception is a versioned App packaging update containing the new
catalog while leaving Manager logic unchanged. A durable alternative is an
explicitly authorized built-in remote-catalog refresh feature. Neither has been
implemented or deployed under the current no-rebuild constraint.

## Historical first bounded control and recovery

The reviewed client passed two stable, read-only refreshes. The first test sent
only a one-percentage-point Channel A reduction and the app-derived Manual
command. The immediate fresh-connection readback failed; a later read confirmed
the exact changed channel set and Manual mode. The harness stopped without
automatically overwriting an unknown state, but its initial failure path did not
complete restoration inside ten seconds. This is a failed safeguard outcome,
not a successful bounded control test.

Private monotonic timestamps show the channel restoration command was sent
514.9 seconds after the initial write and its readback was confirmed at 517.0
seconds (about 8 minutes 37 seconds). Original Automatic mode was confirmed at
608.7 seconds (about 10 minutes 9 seconds). The ten-second limit was exceeded
substantially; these timings must not be described as a successful bounded test.

A separate, guarded recovery first required fresh state to equal the known test
result. It restored the original six values, but Automatic mode did not apply
in that sequence. A subsequent mode-only recovery kept its connection open for
a bounded response and then independently read the original values and Automatic
mode. Recovery passed. There was no channel sweep, shutdown, schedule write,
Shelly action or further control testing.

A later read-only check still reported Automatic mode but different channel
values than the original snapshot. Those later values were not overwritten;
the integration cannot identify their cause conclusively from these packets.
Recovery's original-value match is evidence at the recovery time, not a claim
that automatic operation freezes those values indefinitely.

The exact cause of immediate reconnect failure and command-sequence behavior is
unresolved. HA-side SSH/netcat transport lifetime, controller timing, and actual
firmware behavior must be distinguished with read-only investigation before a
revised bounded plan. Do not silently add command retries or claim a timing fix.
The public candidate keeps its write-profile allowlist empty, so no production
control path can write to this or any other controller.

Native setup describes the read-only candidate. Six Number values remain
available; channel/mode actions fail explicitly as unvalidated before calling the
client. A Write support diagnostic distinguishes this state from a network outage.

Resume requires a reviewed restoration procedure that handles an uncertain
command within the bounded window and does not overwrite competing changes;
successful small-change/readback/restoration tests for all six channels;
and an authorized path to deliver catalog metadata to the installed Manager.
Actual setup, update/rollback/removal, Manager-off operation and Mac-off operation
remain NOT_TESTED. No optical or calibrated output claim follows from byte reads.

## Historical 0.1.0 candidate publication

Source checkpoint `56a0b81c31beddcecf56a96e6027d80d0293de57` contains the native
read-only candidate, tests, builder and usage/recovery documentation. Its remote
SHA matched and [hosted CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34284413351),
including the separate native HA test job. The first evidence/privacy checkpoint
is `a8f717681dca6ed2f3336bd2b80157a9aec57f8f`.

The independently versioned artifact is `aquarius-plant-led-0.1.0.zip`, built
directly from that source commit with fixed ZIP metadata. SHA-256:
`b65d2ce15ea64529d1b33a988c78d32454c48dce55d4f5b64fd195af1cbf9777`.
The release is explicitly a prerelease and its catalog description says read-only.
[Published candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.1.0):
the ZIP, catalog snapshot and SHA256SUMS were downloaded again without credentials;
all three matched the uploaded bytes. The actual Manager archive validator accepted
the downloaded ZIP in an isolated local staging directory. This does not constitute
installation through the live Manager or native test-dev HA acceptance.
The canonical Manager build-context catalog copy is synchronized in source;
the installed App image and Manager runtime logic are unchanged.

## Intended scope

Native host/port setup and reconfiguration; one device with six A–F percentage
Numbers; fresh serialized read-modify-write and confirmed manual operation;
explicit return to automatic program; diagnostic unknown modes; read-only setup,
polling, reconnect and reload; independently versioned pure-Python module.
Schedules, effects, clock/temperature claims, provisioning, firmware changes,
Shelly control, calibrated optical output and RGB colour-wheel control are excluded.

Completion requires separately reported synthetic tests, device readback,
physical observations and actual HAHAPent/native HA lifecycle evidence.

## Continuation read-only lifecycle acceptance

**PASS (actual test-dev):** native setup of 0.1.1 created one loaded entry,
one device, six numeric percentage entities and Automatic-program mode. The
write-support diagnostic reported `read_only`; its missing translated name
was a presentation defect repaired for the final 0.2.0 source.

Manager's actual Ingress UI rolled 0.1.1 back to 0.1.0. After the gated Core
restart, the existing entry loaded with the same device and entity identities,
six readable percentages and Automatic mode. The broken historical 0.1.0
new-entry form was not used or counted as passing. Manager refused removal
while the native HA entry existed. Native HA's entry menu then deleted only
the Aquarius entry, and Manager completed package removal. Final working
installation and acceptance are recorded above. These lifecycle operations used only the
read-only releases and issued no lamp control commands.

## Working control source and immutable publication

Source `8fd50282111fe6eb3c02f0a00ac3716eb31e84d0` prepares module **0.2.0**
with exactly the validated controller/version/six-channel write profile.
Shutdown and unknown operating modes remain readable but cannot initiate or
receive explicit controls. The missing translated write-support name is fixed.
Independent source review **PASS**; local **343 unit tests PASS** and **56 native
HA tests PASS**. [Source CI](https://github.com/djeZo888/HAHAPent/actions/runs/34291685273)
completed successfully, including both Python versions, native HA and the actual
amd64 App image/runtime checks. No private credentials were used by CI.

The deterministic 0.2.0 ZIP SHA-256 is
`9658f034c69fc3cbb5743759920d4f91e4a6429491ed286ee158e4f6e8562382`.
Publication and actual deployment verification passed. A second fresh
pre-deployment encrypted backup was downloaded privately (46,254,080 bytes),
and isolated decryption and selected-content readability passed using the
existing retained recovery key. No live restore was performed.

[Module 0.2.0](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.2.0)
was published as an immutable control candidate with ZIP, catalog snapshot and
checksums. All three unauthenticated public downloads matched their local bytes;
Manager's real archive validator accepted the ZIP and provenance. Artifact
content and release notes passed secret/private-target scanning. Following final native
HA acceptance, its release status was promoted without changing the tag or assets.

The HA-adapter handoff repair subsequently passed independent source review and
**22 adapter tests** (18.913 seconds independently), plus **65 combined worker
and adapter tests** (60.676 seconds by the coordinator). The new adapter closes
its observer connection before each native HA delegation, including Automatic
cleanup; the original deadline, fresh readback and uncertain-completion failure
rules remain intact. The exclusive-connection regression failed on the previous
implementation and passes after the repair. See the superseding frozen hashes
in [the review](../docs/aquarius-validation-review.md). The installed module and
its immutable ZIP are unchanged by this operator-tool repair.

## Final installed state and checkpoint

**PASS (actual):** Manager 0.1.2 is running again, module 0.2.0 remains installed
and configured, all six native channel controls are available, and the lamp is
in Automatic-program mode. Core 2026.9.1 is running; KNX is connected with its
project and startup configuration unchanged. A new dedicated lamp dashboard
renders six channel controls and the operating-mode selector with no unavailable
entities. Existing dashboards were preserved. Private owner handoff contains the
actual dashboard/device locations and entity IDs; none belong in public Git.

The 0.2.0 release was promoted after actual acceptance. Its original tag, ZIP and
all three assets remain unchanged; the canonical catalog points to the current
usage guide and records validated native acceptance. Historical read-only
releases remain immutable. No later cleanup removes or disables the working
integration.

Worker-fix CI 34292965170 ran 346 Linux tests and failed only a portability
assertion expecting a connection reset where Linux returned EOF. The final
regression accepts exactly those two terminal-close outcomes while retaining
its blocked-connection, unchanged-state and no-write checks. Three affected
local tests and independent coordinator review passed; both executable workers
are unchanged. Final publication/merge requires completed successful GitHub
checks for the final task-branch head. The earlier failed CI run is retained,
not relabeled as a pass.

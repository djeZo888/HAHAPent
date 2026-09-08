# Task 003 — Aquarius Plant LED

Status: **IN PROGRESS — authorized continuation to working installed controls**.
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
been executed; the offline/review gate remains pending.

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
These are synthetic checks. App update and live cache persistence remain pending.
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
module configuration and remaining lifecycle actions are pending.

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
| F | +1 point | PASS | FAIL within bound; later deliberate recovery PASS | about 53.16 s total |

Each A–E test independently read the exact changed vector and Manual mode,
restored and confirmed all original channels, then separately restored and
confirmed Automatic. Subsequent read-only checks passed. Positive one-point
changes were used where the current channel did not permit a reduction.

F's changed state was confirmed at 0.716 seconds. Its first fresh recovery guard
read timed out after 0.8 seconds, and the worker ended at 1.518 seconds without
using the remaining recovery reserve. The sequence stopped; a separate guarded
recovery required current state to match the known test change, restored the
original channels and Automatic, and confirmed both. That recovery transaction
took 1.887 seconds. Total excursion is estimated at 53.16 seconds using HA-side
report modification times plus the initial excursion timing; it is approximate,
not a monotonic cross-process measurement. Two subsequent read-only checks
confirmed Automatic. This is a second failed bounded test, not six-channel
acceptance. No released write profile is enabled.

The immediate defect is abandoning cleanup after a single transient recovery
read failure. Whether the timeout occurred at connection setup or queried reply
is not established by that report. Repair requires bounded read-only retries
while reserving command/recovery time; no write retry, stale replay, or larger
ten-second allowance is authorized. Further experiments remain paused until
that repair passes offline tests and independent review. Safe implementation,
publication and read-only native lifecycle work continue.

The interim 0.1.1 module source adds response-backed write-connection lifetime,
strict echo quarantine, fresh-socket confirmation, current Automatic vector
preservation and a three-second admitted-action deadline covering debounce and
lock queues. All profiles remain read-only. Local synthetic checks: **304 unit
tests PASS**, **47 native HA tests PASS**, Ruff/catalog/bundle checks PASS.

## Native setup serialization repair

Actual native HA setup for the unchanged 0.1.0 artifact returned HTTP 500 before
showing the controller form. Private Core diagnostics identified HA's inability
to serialize the `_normalize_host` callable inside the form schema. Direct
FlowManager tests had not exercised the HTTP response serializer.

The unpublished 0.1.1 source now exposes a declarative string field and performs
normalization/validation after submission, retaining normalized duplicate checks
and a clear `invalid_host` field error. Six regression cases use HA's actual
`FlowManagerIndexView._prepare_result_json` for initial/reconfigure forms and
invalid-host responses. **14 config-flow tests PASS; 53 total native HA tests
PASS; Ruff PASS.** These are synthetic framework checks; the repaired artifact
must still pass the real native UI after delivery. The original 0.1.0 release
remains unchanged. Read-only lifecycle order will update its installed code to
0.1.1 before native configuration, then verify rollback using that existing
read-only configuration before removal.

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

## Failed bounded control and recovery

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

## Candidate publication

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

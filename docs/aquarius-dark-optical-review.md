# Dark-baseline optical worker independent review

Review date: 2026-09-09. Status: **PASS — independent offline gate for the
exact worker below**. This gate covers a bounded operator procedure, not actual
lamp output, camera interpretation, native Home Assistant services, or a colour
mapping. The coordinator retains operational authority.

The reviewed procedure and timing decision are documented in
[aquarius-dark-optical-plan.md](aquarius-dark-optical-plan.md). It preserves the
frozen Task 003 and earlier Task 004 workers. The reviewer inspected public
source and ran only deterministic and loopback synthetic checks; no protected
target, credentials, camera, Home Assistant, or actual lamp was accessed.

## Frozen source and independent checks

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_dark_optical_validation.py` | `9aeb4ad86f009594eb75014158b44bfabc8a01e6d1f1c42f644e074bf5ec83a0` |
| `tests/test_aquarius_dark_optical_validation.py` | `076d8883b9bf2bbd2f5ebb55a6ef2055bd99fd6ad9390ddef793566201c10578` |
| Imported `tooling/aquarius_task004_validation.py` | `fb8994bad022e815b779951c032c979b23c51bc04773569f1b57d6789a495047` |
| Imported `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_dark_optical_validation -q
.venv/bin/ruff check tooling/aquarius_dark_optical_validation.py tests/test_aquarius_dark_optical_validation.py
```

Independent result: **21 tests PASS in 5.879 seconds; Ruff PASS**. All four
hashes matched the frozen handoff before and after review. The suite covers
all six selected channels, exact original-vector restoration, preparation and
hold admission deadlines, handled stop flags, lost barriers and independent
reads, phase-specific competing changes, transient contradictions, complete
0.8-second modeled recovery-read timeouts, reserve exhaustion, interrupted
sends/quarantines, and buffered reporting. Two tests use native TCP against an
exclusive loopback device, including fragmented command echoes and a one-time
lost Off processing reply.

An additional independent native loopback probe returned only the first nine
bytes of the first queried Off system reply, then answered later queries
normally. The worker reported experiment and recovery **FAIL**, observed the
later normal full Off state, and sent no command beyond the original Shutdown.
This confirms that a later owned-looking state cannot clear a partial-reply
stop. This probe is synthetic and is separate from the 21-test count.

## Finding resolved before this gate

The first candidate allowed both zero and the future sample vector during
Manual cleanup, even before a sample command was admitted. The reviewer
reproduced a one-time Manual read failure while a competing actor selected that
future vector. The candidate then restored the saved original vector despite
never having sent the sample itself.

The final worker permits only exact Manual zero in that phase. The dedicated
regression requires recovery **FAIL**, preserves the competing vector, and
asserts that only Shutdown and Manual mode commands were sent. Sample-phase
ownership is distinct: after a completed processing boundary, zero or the
selected vector may be explained until confirmation; after sample confirmation,
only the exact selected vector is owned. A lost barrier additionally requires
the exact pending target before cleanup can proceed. No unresolved source
finding remains in this review.

## Required execution boundaries

- Require matching complete Manual baseline reads with the exact privately
  configured vector and profile. Persist intent, then obtain another matching
  fresh read. No evidence filesystem operation occurs between that final guard
  and first write, or during the excursion.
- Start the absolute excursion clock before Shutdown. Keep the experiment
  phase at four seconds, the cleanup deadline at 9.5 seconds, and the total
  maximum at ten seconds. The selected channel is an absolute integer 1–5%
  against independently confirmed Manual zero; the hold is at most 0.3 seconds.
  Late preparation skips the sample, and late confirmation skips the hold.
- Confirm Shutdown zero, then Manual zero, then an additional fresh exact
  Manual-zero guard before sending the selected vector. Restore the complete
  original Manual vector once, only after a fresh phase-appropriate guard.
  Never send Automatic or alter a program, clock, preset, or schedule.
- Preserve 4.8 seconds for recovery starting in Shutdown and four seconds when
  already in Manual. Fresh read retries share a 2.5-second stage limit, at most
  three attempts, and the remaining absolute deadline minus the command
  reserve. These are admission limits, not a guarantee during an outage.
- A fully sent command with completed quarantine but lost queried barrier
  fails the experiment. A fresh full exact pending target may permit a distinct
  deliberate cleanup transaction; the uncertain command is never resent.
  Partial/malformed replies, interrupted sends or quarantine, and observed
  competing modes, profiles, or unexplained vectors stop subsequent writes.
- Close each observer before opening the next connection. Do not run another
  lamp observer or controller concurrently. Camera acquisition is independent
  and cannot defer the worker's cleanup.
- Handled signals set a flag. An admitted transaction reaches its bounded
  processing boundary before stopping further experiment stages; cleanup
  ignores additional stop flags. This suite exercises signal intent
  synthetically, not a new detached-process signal test.

An experiment failure remains an overall failure even when recovery is
confirmed. A failed or contradictory recovery must never be reported as a
restoration success. Process death, host loss, persistent transport failure,
unbounded scheduling delay, and competing control can prevent physical
restoration; this worker does not claim otherwise.

Run only the reviewed hashes in the existing detached HA-side runtime with a
fresh private report and the exact protected target/profile. Check fresh
read-only state afterward and stop further experiments on the first failure
until recovery is confirmed and the procedure is repaired/reviewed as needed.
Actual composite timing and optical interpretation remain **NOT_TESTED** by
this gate. Any changed worker or dependency requires a new affected review.

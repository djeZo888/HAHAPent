# Dark-baseline optical validation procedure

This is a separate Task 004 operator procedure. It does not change the frozen
Task 003 or earlier Task 004 workers, the integration, or its three-second native
service deadline. It has no camera access. An operator captures camera frames
independently; a verified percentage is not a verified colour label.

## Timing decision

The coordinator authorized a **4.0-second experiment phase**, beginning before
the first Shutdown command. The independent cleanup deadline remains **9.5
seconds after that first command**, with a **10-second maximum excursion**.
The new phase therefore reserves at least 5.5 seconds for cleanup. The earlier
three-second phase could reject the sample before sending it: the frozen
transport requires 1.8 seconds remaining when admitting a write, while Shutdown,
Manual resume and a further zero-state guard can take more than 1.2 seconds.

The actual earlier Manual-origin Shutdown/zero/Manual-zero/original-vector cycle
finished in 2.746025 seconds. Ordinary optical tests, including a 0.5-second hold,
finished in approximately 2.25 seconds. These are component observations, not an
actual measurement of this new composite procedure.

The deterministic synthetic model uses 0.4-second full reads, 0.03-second fresh
connections, 0.12-second queried processing barriers, the frozen 0.2-second
quarantines and 0.1-second Manual save pause. Its successful cumulative timings
are:

| Confirmed stage | Seconds from first command |
| --- | ---: |
| Shutdown and all-zero channels | 0.77 |
| Manual zero plus additional fresh zero guard | 1.97 |
| Selected channel independently confirmed | 2.86 |
| 0.3-second sampling hold completed | 3.16 |
| Exact original Manual vector restored | 4.48 |

The selected command must begin by 2.2 seconds to preserve the unchanged
1.8-second admission margin. Slower preparation skips that command and enters
cleanup. A late confirmed sample skips its hold and enters cleanup. Camera
capture, file writes and optical interpretation never consume the active
sampling or recovery budgets. Timing evidence supports a bounded attempt; it
does not guarantee restoration during an outage or contradictory device state.

## State and recovery policy

1. Require two matching reads of the exact configured original Manual vector and
   controller profile. Persist intent privately, then require one final matching
   fresh read before starting the excursion clock.
2. Send Shutdown once. Hold the socket through its processing interval and query
   barrier, then independently confirm mode 8 with six zeros.
3. Send Manual once and independently confirm mode 1 with six zeros. Obtain an
   additional fresh exact Manual-zero guard before admitting the sample.
4. Send one declared vector containing only the selected channel at an absolute
   integer 1–5%; every other channel is zero. Save Manual and independently
   confirm the exact selected vector. Hold for no more than 0.3 seconds, only if
   the experiment and cleanup reserves permit it.
5. Freshly guard the owned state before restoring the complete original Manual
   vector once, with a Manual save, processing barrier and independent readback.
   Never send Automatic, change a schedule, or retry a write.

Recovery ownership depends on the reached phase. Before any sample command,
Manual permits only the confirmed zero vector; another controller choosing the
future sample vector does not grant restoration authority. After a sample
command whose processing has settled, zero or the selected vector can be owned
states until the sample is confirmed. After confirmation, any change from the
selected vector is a contradiction. Shutdown recovery permits only mode 8 zero,
then a confirmed Manual-zero transition and additional fresh zero guard.

An early Shutdown-stage recovery read reserves 4.8 seconds for Manual resume and
possible vector restoration. Recovery already in Manual reserves four seconds.
Fresh reads may retry at most three times within their existing 2.5-second read
budget and the remaining stage reserve. Send failures, interrupted quarantine,
partial/malformed replies and contradictory modes/profiles/output latch a stop
on further writes. Later normal-looking reads cannot clear that latch.

A lost queried barrier after a completely sent command and completed quarantine
fails the experiment. Cleanup may continue only when a fresh full read proves
the exact pending target for that phase. Merely observing the original baseline
does not resolve an unrelated pending command. This fallback never resends the
uncertain command. A cleanup barrier lost after an original-vector write may
likewise be confirmed by a fresh exact original-state read.

Signals set a flag. An already admitted transaction reaches its queried
processing boundary before observing that flag; no next experiment stage or
hold starts afterward. Cleanup ignores further stop flags. Private reporting
is buffered throughout the excursion and flushed only after cleanup finishes.

## Evidence gate

The worker and its tests are
`tooling/aquarius_dark_optical_validation.py` and
`tests/test_aquarius_dark_optical_validation.py`. Tests include deterministic
phase faults, one-time barrier/read loss, realistic 0.8-second recovery-read
timeouts, reserve exhaustion, ownership contradictions and actual native TCP
against an exclusive loopback simulator. All are synthetic. The source requires
independent review and exact-hash approval before any actual lamp run. Actual
outcomes and camera interpretation belong in the Task 004 acceptance report.

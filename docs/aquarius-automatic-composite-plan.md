# Automatic-origin native power acceptance plan

This separate Task 004 procedure validates native Resume schedule, Off and On
from the owner's existing Manual output, then restores that exact original
Manual vector. It does not edit the lamp's stored schedule. The implementation
is `tooling/aquarius_automatic_composite.py`; its dedicated tests are
`tests/test_aquarius_automatic_composite.py`.

The current [project instructions](../AGENTS.md) and
[Task 004 record](../tasks/004-aquarius-ux.md) authorize this separately reviewed
mode/power composite with a **twenty-second maximum**, a **six-second experiment
phase**, and a **19.5-second final cleanup/read deadline**. Task 004 requires
Automatic-origin power acceptance without specifying a numerical duration for
this composite. The larger reserve accommodates entering Automatic and
restoring the owner's original Manual mode within one supervised procedure.
It does not change the frozen ten-second optical or single-action workers,
the separate four-second dark optical phase, or the runtime's three-second
explicit-action deadline. Only the coordinator may execute an actual run.

## Timing and admission

The excursion clock starts before the first native Resume request. Experiment
HTTP requests and independent TCP/HA reads share its six-second deadline;
cleanup has the separate absolute deadline of start plus 19.5 seconds. At least
13.5 seconds therefore remain for cleanup when the experiment phase ends.
Normal completion within ten seconds remains the operating goal.

Actual isolated Task 004 native measurements, supplied by the coordinator:

| Completed native operation | HTTP completion | Independent TCP confirmation |
| --- | ---: | ---: |
| Resume schedule | 1.027578 s | 1.372238 s |
| Manual-origin Off | 1.407147 s | 1.727962 s |
| Manual-origin On, including saved-vector restoration | 2.010279 s | 2.331222 s |

Their combined 5.431422-second confirmation time is a planning reference,
not an executed composite result or an upper bound. Two additional fresh
ownership guards before Off and On cost roughly 0.64–1.04 seconds using prior
0.322–0.520-second native read measurements. Adding those guards to the
Manual-On reference exceeds six seconds before HA entity GETs. Automatic-origin
On has fewer commands than Manual restoration, but its actual duration remains
unmeasured before this procedure. Thus the six-second phase admits only a fast
enough observed path; these measurements do not establish a guaranteed fit.
Additional HA entity GETs consume the same six-second phase.
Each new native action requires at least 1.8 seconds of remaining phase time;
otherwise it is skipped and cleanup begins. Each service HTTP deadline is
also capped at three seconds from dispatch. No camera processing, file flush,
user interaction, SSH lifetime or external process participates in the active
phase or cleanup allowance.

Recovery in confirmed Automatic reserves four seconds after its fresh state
guard. Recovery from confirmed Off-zero reserves 4.8 seconds for Manual resume
and possible original-vector restoration. Bounded fresh reads may retry at
most three times within the existing 2.5-second read budget and the remaining
command reserve. A deadline can stop further commands; it cannot guarantee
restoration during an outage or competing control.

## Required observations and ordered actions

1. Require two matching TCP reads of the exact configured original Manual vector
   and controller profile. Read the configured native mode-status and Light
   entities to confirm Manual override, logical On and validated power support.
   Persist the original state and declared Resume/Off/On intent privately, then
   obtain a final matching fresh TCP baseline before starting the excursion.
2. Release the TCP observer before invoking the exact configured Resume button
   through HA. Require successful HTTP completion, fresh independent TCP mode 0,
   and native HA mode status `following_schedule`.
3. After the HA mode-status GET, freshly confirm TCP Automatic and the exact
   profile again; program channel drift is permitted. Release the observer and
   invoke native Light Off. Require HTTP completion and
   an independent full TCP mode-8/all-zero state. Read the native Light state and
   require `off`, validated power support, and the exact `on_behavior` value
   `On resumes the lamp's stored schedule`.
4. That attribute is computed by the integration from a confirmed, matching
   saved Automatic Off origin. The different missing-memory fallback text does
   **not** satisfy this gate. After this HA GET, obtain another fresh exact
   mode-8/all-zero/profile guard before releasing the observer and invoking
   native Light On. Require HTTP completion, independent TCP Automatic, native
   mode status `following_schedule`, and native Light On.
5. Independently guard the current owned state before deliberate cleanup. From
   the Automatic program started by this procedure, raw mode/profile must still
   match; channel percentages may follow its schedule. Send the exact original
   six-channel vector once with a Manual save and processing barrier, then
   confirm the complete original Manual state on a fresh TCP connection.

If a known rejected/undelivered action or read-only HA observation fails after
confirmed Off, cleanup requires fresh mode 8 with six zeros. It sends Manual
once, confirms its processing barrier and independent output, and accepts the
exact original vector if already present. Otherwise only confirmed Manual zero
plus another exact fresh Manual-zero guard permits one original-vector/Manual
save. Changed output or competing mode/profile forbids replay. Cleanup before
any known mutation requires the exact original state and sends no commands.

The worker releases its observer before every native service **and** state GET.
The lamp's exclusive connection behavior has previously been observed; the
worker must not hold a competing observer while HA acquires its own socket.
Native entity IDs and config-entry/device mapping must be verified privately by
the coordinator. Prefix validation alone does not prove registry ownership.

## Failure boundaries

HTTP 200 is service completion evidence; it is never sufficient lamp-state
proof. Missing, malformed, redirect, server-error or timed-out service responses
remain **UNKNOWN**. After any UNKNOWN, this composite sends no further HA
request and no raw restoration command. A bounded precautionary wait and fresh
read-only observations may describe the state, but cannot prove that HA rejected
or cancelled a task, even when the exact original state is later observed. The
run and its recovery remain FAIL. A dropped HTTP connection does not cancel HA's
shielded service execution. Recovery reserve never changes this boundary.

Observed partial/malformed replies or competing mode/profile latch a stop on
further writes. A later normal-looking read cannot clear that latch. A complete
wrong reply followed by transport loss is also retained as a contradiction.
Unknown actions are never repeated, schedules are never uploaded, and cleanup
never follows an unexplained mode change.

After a fully sent cleanup command and completed processing interval, a lost
queried barrier may be confirmed by bounded fresh full-state reads. Exact
original state is required before reporting restoration. Interrupted send or
processing interval, partial/ambiguous replies, or contradictory state are
terminal. Writes themselves are never retried. Signals set a flag; no next
experiment action starts afterward, and guarded cleanup ignores subsequent
signals. Report writes are buffered during the excursion; preflight persistence
failure blocks dispatch, and final persistence failure does not interrupt
completed cleanup.

## Synthetic evidence and execution gate

The dedicated suite includes deterministic phase/deadline faults, saved-origin
versus fallback behavior, true HTTP-200 ignored actions, one-time contradictory
system replies followed by EOF, competing cleanup state, unknown late On,
report failures, cleanup barrier loss, and the extra Manual-zero ownership guard.
Real loopback HTTP endpoints act through their own TCP sockets against an
exclusive TCP simulator; they also serve the exact HA-style Light/mode-status
readback. This verifies transport composition and observer handoff using real
sockets. The HTTP simulator is **not the Home Assistant framework** and none of
these tests establish actual native HA, persisted-origin or lamp acceptance.

Author verification: **27 tests PASS in 20.007 seconds; Ruff PASS**. The worker
SHA-256 is `a676683e9bf90033c3e9b8ed60b647d806ffb0432f43ba31db158b707db2d4db`;
the test SHA-256 is
`1c4cb9f5fc0c29eb3b4e8a0dd5ae5898084d7b4ae76b13f1cfd8a6ae1f55699e`.
Independent review and actual composite execution remain separate gates.

Run the isolated synthetic checks with:

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_automatic_composite -q
.venv/bin/ruff check tooling/aquarius_automatic_composite.py tests/test_aquarius_automatic_composite.py
```

Before execution, require passing dedicated tests and an independent review of
the exact source/dependency hashes. Use only the protected selected test-dev
origin, configured Aquarius entities and expected original Manual vector;
configuration and reports remain owner-only outside Git, and the token enters
through stdin memory only. Launch the worker detached on HA-side access. Final
acceptance requires actual HTTP/TCP/HA-origin observations, exact original
Manual recovery within the declared bound, and separate fresh post-read checks.
A failure stops further experiments pending documented recovery and review.

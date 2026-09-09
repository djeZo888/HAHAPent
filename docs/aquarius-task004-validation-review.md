# Task 004 validation-worker review

Review date: 2026-09-09. Status: **PASS — independent offline gate for the
bounded Task 004 worker below**. This is not actual lamp, camera, or native HA
control validation. The coordinator retains all operational authority.

The independent review covers `tooling/aquarius_task004_validation.py` and its
synthetic tests. It does not access the lamp, Home Assistant, camera, protected
configuration, credentials, or private evidence. Synthetic results do not
establish a colour mapping or prove the controller's software Shutdown behavior.
The frozen Task 003 transport and recovery helpers retain their separate review
in [aquarius-validation-review.md](aquarius-validation-review.md).

## Frozen source and independent evidence

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_task004_validation.py` | `fb8994bad022e815b779951c032c979b23c51bc04773569f1b57d6789a495047` |
| `tests/test_aquarius_task004_validation.py` | `714694237b167fd8571926471a401f282aa980c3579b04befb0d4ac20cd7a8fc` |
| Imported `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| Unchanged `tooling/aquarius_ha_validation.py` | `7669e3c363cd1c9a38b39cd54d3dd89c3047a787a10e27c585e72a4bd686045b` |

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_task004_validation -q
.venv/bin/ruff check tooling/aquarius_task004_validation.py tests/test_aquarius_task004_validation.py
```

Independent result: **36 tests PASS in 27.983 seconds; Ruff PASS**. Hashes were
checked against the frozen author handoff. The tests use a deterministic
simulator and native loopback TCP, including a server that rejects simultaneous
connections. They cover both original modes, retained and all-zero Shutdown
responses, modest optical sampling, durable-intent drift, handled interruption,
transient and persistent read failures, lost write barriers, unknown profiles,
competing modes/vectors, partial frames, query echoes, and guarded Manual-zero
restoration. A source or dependency change invalidates the affected gate and
requires review and tests again.

## Required boundaries

- Select only the explicitly configured target and profile. No discovery,
  provisioning, firmware, clock, schedule upload, or unrelated device control.
- Start from matching complete baseline reads, persist the intended bounded
  action, then recheck the baseline before the first write. Evidence storage must
  not consume the excursion's cleanup allowance.
- Keep optical sampling within the configured modest percentage and duration
  limits: selected output 1–20%, a single-channel delta of at most five
  percentage points, and at most two seconds of sampling inside the three-second
  experiment budget. The worker records a sampling interval; it cannot claim to
  measure a colour or observe a camera.
- Keep a single absolute excursion deadline and reserve time for fresh guarded
  restoration. Retry only bounded fresh reads after transport failures. Never
  repeat an uncertain write or reinterpret malformed, partial, echoed,
  contradictory, or competing state as permission to restore a snapshot.
- Close the previous observer connection before opening the next connection.
  No parallel observer may hold the lamp's exclusive TCP connection while a
  controller or cleanup worker needs it.
- For an Automatic-origin Shutdown probe, accept only the baseline-retained or
  all-zero vector under the exact profile and mode 8. Guard the observed Off
  vector again before one deliberate Automatic command. Do not replay channel
  percentages into the stored program; after independently confirming Automatic,
  its program may legitimately advance the output percentages.
- A Manual-origin probe must start in matching Manual state and must never
  switch to Automatic. After a fresh exact Off-state guard, first send only
  Manual. An exact original vector confirms recovery with no channel writes.
  Only an all-zero Off vector followed by an explicitly queried Manual barrier,
  a fresh complete Manual-zero state, and another fresh exact Manual-zero guard
  permits one deliberate original-vector-plus-Manual restoration. A retained
  Off vector that unexpectedly becomes zero after Manual is a contradiction.
  Lost Manual barrier or independent confirmation cannot authorize a vector
  replay. Reserve 4.8 seconds before admitting Manual and retain three seconds
  for its possible guarded snapshot restoration.
- Treat interruption as a request to stop experimentation and enter guarded
  cleanup. Further handled signals must not bypass that cleanup. Process death,
  power loss, and persistent network loss cannot guarantee physical restoration.
- Report experiment and recovery independently. A failed experiment with
  confirmed recovery is still an overall failure.

## Findings resolved before the frozen gate

The first review reproduced two one-time native TCP contradictions during a
Shutdown experiment: a wrong profile in a fresh system reply, and a competing
Manual reply followed by a lost channel response. The original candidate could
subsequently see normal Off state and send Automatic during recovery. Persistent
fault tests had not exposed this boundary. The final candidate latches unsafe
experiment observations and checks a system mode already observed before a
transport failure. One-time native profile, partial-frame, channel-query-echo,
and competing-mode-plus-EOF regressions now require no restoration write even
when a later fresh read is otherwise normal.

The final candidate also checks a fresh prewrite guard after durable intent,
without subsequent evidence fsync before the excursion, and applies the unsafe
observation latch to optical experiments. Native optical regressions cover a
one-time wrong profile and a competing mode whose channel reply is then lost.
The separately authorized Manual-origin extension follows the stricter policy
above; its simulator and exclusive-connection TCP cases are included in the
36-test result. Neither frozen Task 003 worker was changed.

## Conditions for bounded execution

Use the exact reviewed worker detached in the existing HA-side runtime with
the protected explicit target/profile, new private report, and chosen action.
An Automatic or Manual probe must match the freshly observed original mode;
the tool does not change the owner baseline to fit a test. Release any other
lamp observer connection before admitting the test. Camera acquisition is
independent and cannot postpone local cleanup.

The experiment deadline is three seconds after excursion admission; cleanup
ends at an absolute 9.5 seconds, and recovery PASS requires independent state
confirmation within ten seconds. Fresh read retries share the same absolute
deadline, at most three attempts and 2.5 seconds per read stage, while preserving
any remaining command reserve. No write is retried. Signal handling reuses the
reviewed base flag/cleanup behavior; this new suite exercises interruption
synthetically, not a new detached-process signal trial.

Require the worker's experiment and recovery confirmations, bounded reported
time, and subsequent fresh read-only checks. Stop on the first failure or
uncertain restoration; diagnose and confirm recovery before another experiment.
All-zero initial percentages cannot establish whether Shutdown retains channels.
The shipped power-profile allowlist and any colour labels require separate
actual evidence; this offline gate does not enable them. The worker cannot
guarantee physical restoration under unhandled process death, host loss,
persistent network failure, or competing device control.

## Related UI checks

The per-lamp label options use generic Channel A–F defaults and stable Number
unique IDs. Native HA 2026.9.1 config/options tests passed **35 tests**, including
an actual options reload with synthetic confirmed Off memory. The stored
payload/revision, Manual restoration choice, and entity IDs remained unchanged;
no power, channel, or mode command was issued. These tests use mocked device
transport and HA's synthetic storage fixture.

[The generic dashboard example](examples/aquarius-tile-dashboard.yaml) uses six
native Number Tile sliders, a software-power Tile, a read-only mode Tile, and a
deliberate Resume schedule action. Its YAML parses and its feature configuration
was checked against the frontend source version packaged with HA 2026.9.1.
No actual dashboard interaction or Recorder configuration change is claimed by
this source review.

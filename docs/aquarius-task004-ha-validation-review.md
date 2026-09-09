# Task 004 native HA acceptance-worker review

Review date: 2026-09-09. Status: **PASS — independent offline gate for the
frozen service transport and worker below**. This review performs no actual
lamp, HA deployment, camera, or browser operation. The coordinator retains
operational authority and records actual acceptance separately.

## Frozen source and independent evidence

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_task004_ha_service.py` | `ab57efce00f02fe75237ae8bcf2bde0484e47675d5bbe2055ac9a01c4ad1f66a` |
| `tooling/aquarius_task004_ha_validation.py` | `a87a382c2108dfb4c117586eef40685fabb60d42f3c570940cb02932a9853a53` |
| `tests/test_aquarius_task004_ha_service.py` | `5d73150b93f46d03ed84c06c09d85f9974d645c3b56449c98821581ef42aa61e` |
| `tests/test_aquarius_task004_ha_validation.py` | `cd99786f12e81a1fd46348d456408439a7aa9674f5434b9be931a3d2cd3bd952` |
| Imported `tooling/aquarius_task004_validation.py` | `fb8994bad022e815b779951c032c979b23c51bc04773569f1b57d6789a495047` |
| Imported `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| Imported `tooling/aquarius_ha_validation.py` | `7669e3c363cd1c9a38b39cd54d3dd89c3047a787a10e27c585e72a4bd686045b` |

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_task004_ha_validation tests.test_aquarius_task004_ha_service -q
.venv/bin/ruff check tooling/aquarius_task004_ha_validation.py tooling/aquarius_task004_ha_service.py tests/test_aquarius_task004_ha_validation.py tests/test_aquarius_task004_ha_service.py
```

Independent result: **29 tests PASS in 21.020 seconds; Ruff PASS**. A subsequent
test-only change split a synthetic invalid URL literal without changing its
constructed value; the final 14 service tests passed again in **0.165 seconds**.
All executable hashes remained unchanged, and the final seven hashes above were
checked after testing. Changes invalidate the affected review and test gate.

The tests use deterministic simulation, real loopback HTTP, and a synthetic
TCP lamp that rejects simultaneous connections. They exercise all six Number
routes, Manual and Automatic Off/On, retained and zero Off responses, Resume
schedule, wrong Manual output after completed On, handled interruption,
transient contradictory state, undelivered actions, unknown Off/On/Resume
completion, and late server effects after HTTP timeout. The HTTP server models
HA service effects; it is not an actual HA framework instance. Native HA
framework and storage evidence is recorded separately in the
[runtime review](aquarius-task004-runtime-review.md).

## Reviewed routing and privacy

The private configuration selects one explicit private IPv4 lamp and HA origin,
one action, and exact supported Aquarius entity IDs. The Number must match the
configured A–F channel. Each transaction can invoke only its selected service
family: Number `set_value`, Light `turn_off`/`turn_on`, or Button `press`.
There is no brightness, colour, Select, generic service, discovery, or alternate
destination route. Registry ownership and the selected entry's lamp target
remain mandatory coordinator preflight checks; an entity-name pattern alone
cannot prove device ownership.

The bearer token is bounded and validated, arrives through stdin, and remains
in process memory. Configuration and reports use the existing owner-only file
checks. No token, authorization header, raw HTTP error body, or private target
is printed in errors. HTTP uses the fixed origin, does not follow redirects,
and bounds headers and each operation. HTTPS uses the default verified TLS
context. No real TLS endpoint or credentials were exercised by this review.

## Reviewed transaction safeguards

- Matching complete preflight states and a fresh guard after durable intent
  precede every experiment. Power probes must start in their selected original
  Manual or Automatic mode. Resume validation starts in Manual and preserves
  that original snapshot for deliberate bounded cleanup.
- The observer socket closes before every HA request. An independent full
  system/channel read opens only after HTTP completion, so the observer cannot
  occupy the lamp's exclusive TCP connection while HA controls it.
- Every HTTP request is bounded by both its current phase deadline and three
  seconds from that request's start. The experiment ends within its original
  three-second allowance; cleanup retains the same absolute 9.5-second deadline.
  Recovery PASS requires independent confirmation within ten seconds. Evidence
  fsync remains outside the active excursion.
- Native power acceptance sends Off through the configured Light, verifies
  mode 8 with retained or zero channels, freshly guards that state, then sends
  native On. Manual recovery must independently match the exact original mix.
  If HTTP-completed On returns Manual with the wrong zero vector, the worker
  reports failure and does not fabricate the direct worker's Manual-barrier
  permission to send a raw snapshot. Automatic recovery confirms original mode
  0 without replaying a brightness vector; its running program may advance.
- Number acceptance verifies exactly the requested one-channel change and
  preserves the other five. Its guarded direct cleanup restores the original
  vector and mode. Resume acceptance verifies Automatic, then deliberately
  restores and independently confirms the original Manual snapshot; it does
  not upload or alter the stored automatic program.
- Contradictory profile, mode, vector, query echo, or partial state cannot be
  forgotten when a later read succeeds. A latched unsafe observation permits
  diagnostic reads only. A known rejected or undelivered experiment cannot
  authorize overwriting a subsequently changed state.
- No HA request or uncertain write is retried. Unknown completion of the initial
  Off, Number, or Resume request allows only the existing bounded settling
  interval and freshly guarded direct cleanup where that action's policy permits
  it. The overall result remains FAIL even if the original state is observed.
  Unknown completion of the cleanup On request permits only bounded read-only
  observation afterward: no second service request or raw snapshot replay.
- Handled stop signals end experimentation and enter guarded cleanup. Further
  signals do not throw through cleanup. A failed or interrupted experiment
  remains an overall failure even when recovery is confirmed.

## Operational limits

The installed HA 2026.9.1 API implementation was inspected locally: its service
endpoint awaits a blocking service call and shields that call from cancellation
when the HTTP connection drops. Thus HTTP 200 establishes service completion,
while a timeout cannot establish cancellation or exclude delayed admission.
Independent lamp readback is always required, and the settling interval is not
proof that a delayed HA task cannot subsequently execute.

Before bounded execution, the coordinator must verify the installed runtime,
exact entity-to-entry/target mapping, current healthy HA state, original mode,
and exclusive access to the lamp connection. Run the reviewed worker detached
with a new private report. Require the reported service completion, independent
experiment and recovery state, elapsed bound, and subsequent fresh read-only
checks. Stop on any failure or uncertain restoration before another experiment.

This gate does not cover an externally armed browser interaction, optical
isolation, camera colour identification, persistent network loss, process or
host death, or physical restoration guarantees. Those require separate evidence
or review; none is inferred from these synthetic passes.

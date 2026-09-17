# Compact acceptance worker independent review

Review date: 2026-09-17. Status: **PASS — source and synthetic gate only**.
The coordinator reviewed the separately authored worker, its inherited transport,
deadlines and reporting, and independently ran its 37 tests: PASS in 29.989 seconds.
Actual Home Assistant/lamp acceptance is recorded separately in Task 005.

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_compact_validation.py` | `d3b943a5f02030852398f3e62d6a07fc188f91230b5d404fb719014a184749b3` |
| `tests/test_aquarius_compact_validation.py` | `2b0d906920cc85b6bf9e0e4e419a5210ef7f8e9839f4d6310fab114a665c92fa` |
| `tooling/aquarius_automatic_composite.py` | `a676683e9bf90033c3e9b8ed60b647d806ffb0432f43ba31db158b707db2d4db` |
| `tooling/aquarius_task004_ha_service.py` | `ab57efce00f02fe75237ae8bcf2bde0484e47675d5bbe2055ac9a01c4ad1f66a` |
| `tooling/aquarius_task004_validation.py` | `fb8994bad022e815b779951c032c979b23c51bc04773569f1b57d6789a495047` |
| `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| `tooling/aquarius_ha_validation.py` | `7669e3c363cd1c9a38b39cd54d3dd89c3047a787a10e27c585e72a4bd686045b` |

```sh
.venv/bin/python -m unittest tests.test_aquarius_compact_validation -q
.venv/bin/ruff check tooling/aquarius_compact_validation.py tests/test_aquarius_compact_validation.py
```

No unresolved source finding remains. The new procedure does not inherit the
old snapshot-restoring recovery routine. It sends native HA colour/Intensity
actions and permits at most one raw Automatic-only cleanup command. It contains
no channel-vector restoration. Expected vectors are independently supplied by
the operator; the worker and tests do not import the production colour mixer.

The initial state requires matching complete Automatic reads, an exact profile,
no channel above 5%, native schedule status and a fresh post-persistence guard.
The operator must verify the exact entities belong to the same configuration
entry and lamp; a matching name prefix alone is insufficient. Close the exclusive
TCP observer before HA operations. Recheck exact ownership before later actions
and before cleanup. A changed profile, mode, vector or contradictory partial
reply permanently prohibits subsequent writes, even if a later read looks valid.

HTTP completion and independent complete lamp readback are separate gates.
An uncertain HTTP result or unexpected adapter failure latches UNKNOWN. This
permits only bounded settling and read-only observation, never another service
or recovery command. A known pre-delivery failure or explicit rejection may
permit cleanup only after a fresh exact owned-state guard. Already-active
Automatic is preserved; its schedule may change percentages without inviting
snapshot replay. A lost cleanup processing reply can be confirmed by fresh reads,
but the cleanup command is never repeated.

One action has a three-second experiment, 9.5-second cleanup deadline and
ten-second maximum. Two or three actions share a six-second experiment,
19.5-second cleanup deadline and twenty-second maximum. There is no deliberate
hold. Every service has at most three seconds within the experiment deadline,
and the inherited 1.8-second dispatch admission margin remains mandatory.
Recovery read retries retain a four-second command reserve. Signals request
cleanup rather than throwing asynchronously; report writes are buffered during
the excursion. A recovered failed experiment remains FAIL.

Coverage includes immutable configuration, exact routes and entities, literal
zero, invalid ranges, private file permissions, parse-only configuration checks,
signals, stale guards, reporting failures, late service effects, unknown results,
competing state, partial/malformed replies, timing exhaustion, read retries,
ignored cleanup and lost processing barriers. Real loopback HTTP/exclusive TCP
tests exercise all three planned paths and faults; these simulate HA and the
lamp and are not physical-device or native HA framework evidence.

Use the exact reviewed files in a detached HA-side process with private config,
stdin-only token delivery and a new private report. Process/host loss, persistent
network failure or competing control can prevent restoration; software deadlines
cannot guarantee physical recovery. Stop new experiments after any failure until
confirmed recovery and necessary repaired-procedure review. Changed source or
dependencies invalidate the affected gate. Historical worker files are unchanged.

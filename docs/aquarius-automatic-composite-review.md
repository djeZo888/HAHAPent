# Automatic-origin composite independent review

Review date: 2026-09-09. Status: **PASS — independent source and synthetic gate
for the exact files below**. This is not actual Home Assistant, lamp, or stored
Automatic-origin acceptance. Only the coordinator may perform the separately
authorized bounded operation.

The [procedure plan](aquarius-automatic-composite-plan.md) and current
[project instructions](../AGENTS.md) define a separate six-second experiment,
19.5-second cleanup deadline, and twenty-second maximum excursion. Earlier
ten-second optical and single-action workers are unchanged. The review covers
the new composition and its imported cleanup/transport behavior; it does not
expand another procedure's operational authority.

## Frozen files and independent evidence

| File | SHA-256 |
| --- | --- |
| `tooling/aquarius_automatic_composite.py` | `a676683e9bf90033c3e9b8ed60b647d806ffb0432f43ba31db158b707db2d4db` |
| `tests/test_aquarius_automatic_composite.py` | `1c4cb9f5fc0c29eb3b4e8a0dd5ae5898084d7b4ae76b13f1cfd8a6ae1f55699e` |
| Imported `tooling/aquarius_task004_ha_service.py` | `ab57efce00f02fe75237ae8bcf2bde0484e47675d5bbe2055ac9a01c4ad1f66a` |
| Imported `tooling/aquarius_task004_validation.py` | `fb8994bad022e815b779951c032c979b23c51bc04773569f1b57d6789a495047` |
| Imported `tooling/aquarius_validation.py` | `1fbbb2db16a19b7b7478b699903d95bd725710d308a9c37c5114666f0ce38300` |
| Imported `tooling/aquarius_ha_validation.py` | `7669e3c363cd1c9a38b39cd54d3dd89c3047a787a10e27c585e72a4bd686045b` |

```sh
.venv/bin/python -B -m unittest tests.test_aquarius_automatic_composite -q
.venv/bin/ruff check tooling/aquarius_automatic_composite.py tests/test_aquarius_automatic_composite.py
```

The primary independent run completed **27 tests PASS in 20.014 seconds; Ruff
PASS**. A second independent reviewer examined inherited deadlines, phase
ownership, and UNKNOWN completion behavior and ran **27 tests PASS in 20.019
seconds; Ruff PASS**. All six hashes matched the final author freeze and were
rechecked after the runs. Neither reviewer changed worker or test source.

Tests use deterministic state/time fixtures and real loopback HTTP/TCP sockets.
The HTTP service simulator operates through an exclusive TCP device simulator
and supplies HA-shaped entity responses. It is not the Home Assistant framework.
Coverage includes exact Manual baseline and post-intent guards, competing state
between stages, origin versus fallback reporting, ignored HTTP-200 actions,
late/unknown On delivery, signal requests, phase and recovery deadlines, report
failures, partial/contradictory replies, bounded read retry, and guarded Manual
restoration. The native HTTP reader tests also cover route rejection, redirects,
duplicate framing headers, incomplete/oversized bodies, duplicate JSON keys and
nonfinite values, without exposing token or body contents.

## Findings resolved before this gate

The first candidate confirmed TCP state, read HA state, then delegated the next
Off or On without a new guard. The reviewer reproduced a competing Manual vector
introduced during the post-Resume HA GET. The candidate still called Off and
subsequently restored its older Manual snapshot. Its experiment failed, but its
recovery incorrectly accepted overwriting that intervening state.

The repaired worker obtains a fresh owned Automatic-mode/profile guard after
the HA status GET and immediately before Off. It obtains a fresh exact
Off-mode/zero-vector/profile guard after the saved-origin Light GET and before
On. It then closes the observer and rechecks the unchanged 1.8-second action
admission margin. The new regressions require no subsequent service or snapshot
write after competing mode, profile, or Off-vector observations at those
boundaries. Legitimate Automatic program percentage drift remains permitted.

The new JSON reader also initially accepted a response with contradictory
duplicate `on_behavior` attributes, allowing the later value to claim a saved
Automatic origin. A native loopback reproduction confirmed this. The final
reader rejects duplicate keys and nonfinite JSON constants, with negative
response regressions. No unresolved source finding remains in this gate.

## Required behavior and execution conditions

- Begin in two matching complete reads of the exact private Manual snapshot and
  profile. Require the configured native mode-status and Light observations,
  persist intent, and use the inherited fresh exact post-intent baseline guard.
  Evidence filesystem work must not reopen a stale-state window or consume the
  active excursion reserve.
- Use only the configured Resume button and On/Off Light at the exact protected
  HA origin. GETs are limited to the configured Light and mode-status entity.
  The coordinator must verify their actual registry/config-entry/device mapping
  and the installed integration source. Name prefixes alone cannot establish
  ownership. The token enters through stdin and remains in memory.
- After Resume, require independent TCP Automatic plus HA
  `following_schedule`. Recheck the owned raw phase before Off. After Off,
  require independent mode 8 with six zeros and the actual Light attribute
  `On resumes the lamp's stored schedule`, with Light Off and validated power.
  In the reviewed integration this attribute represents a confirmed, matching
  saved Automatic origin. Its distinct missing-memory fallback text cannot pass.
  Recheck exact raw Off state before On, then require independent TCP Automatic,
  HA schedule status, and Light On.
- Release the lamp observer before every service call and HA state GET. No
  competing read-only holder may occupy the device's exclusive TCP connection.
  Each service dispatch has a three-second maximum within the six-second
  experiment deadline. Added guards remain inside that deadline; a slow path
  must skip a later action rather than weaken a guard.
- Freshly guard the reached owned phase before restoring the original Manual
  snapshot. Confirmed Automatic permits schedule-driven percentage drift but
  requires the same raw mode and profile. Confirmed Off permits only the known
  zero vector, followed by Manual mode, its queried processing barrier and an
  independent read. Only confirmed Manual zero plus another fresh exact zero
  guard permits the original-vector/Manual restoration. A competing state or
  partial/contradictory response stops further writes.
- UNKNOWN completion at any service permanently forbids every later HA or raw
  actuator command. A bounded precautionary wait and read-only diagnostic state
  cannot prove cancellation or restore permission, even when the original state
  is observed. Experiment, recovery, and overall status remain FAIL. The larger
  reserve never authorizes a replay of an uncertain action.
- Retry only bounded fresh recovery reads within the remaining absolute
  deadline and stage reserve. Never retry a write. A lost reply after a complete
  cleanup send and processing interval may be confirmed by fresh state only
  where the inherited policy permits it; uncertain Manual-mode processing does
  not authorize a subsequent zero-to-snapshot replay.
- Handled signals stop subsequent experimentation and preserve guarded cleanup.
  Reporting is buffered throughout the excursion. Recovery PASS requires exact
  original Manual state confirmed within the twenty-second maximum; all I/O
  uses the earlier 19.5-second cleanup deadline. A failed experiment remains an
  overall failure even when recovery succeeds.

The plan's separately measured operations are planning references, not evidence
that this six-second composite fits on the actual controller. Use the exact
reviewed files in the detached HA-side runtime with a fresh private report and
confirm the native entity mapping before launch. Actual acceptance requires
all HA/TCP/origin observations, exact bounded Manual restoration, and separate
fresh post-read checks. Stop further experiments after failure until recovery
is confirmed and any necessary repair has been reviewed.

Actual Automatic-origin native power acceptance remains **NOT_TESTED** by this
offline gate. Process death, host loss, persistent network failure, delayed
external service completion, and competing control can prevent physical
restoration. No live/private data or Git mutation was used in either independent
review. Any changed worker or dependency invalidates its affected gate.

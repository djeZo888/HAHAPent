# Aquarius Plant LED 0.4.0 runtime review

Review date: 2026-09-17. Final source review gate: PASS, with no unresolved
finding. Both findings below are repaired and covered by the final frozen runs.

Two reviewers covered distinct author boundaries. The runtime reviewer
independently reviewed the compact client/coordinator changes and their tests;
that reviewer authored the native entity/options changes, so does not claim an
independent review of those files. The coordinating reviewer independently
reviewed the native UX and pure mixer as recorded below. All execution here uses
synthetic state or loopback simulators, with no private credentials or physical
device access. Actual publication, installation and lamp acceptance are separate
gates.

## Reviewed behavior

- A compact gesture builds one complete six-channel target and uses one guarded
  channel write followed by Manual save, a queried processing barrier and an
  independent fresh readback. It does not call six Number setters.
- Ordinary Manual changes require an unchanged profile, mode and current vector.
  Automatic may advance its channel levels; intensity-only uses the fresh full
  vector, including channels excluded from the colour recipe.
- Explicit colour from Off uses the separate validated power profile. It reads
  the exact observed Off state, selects Manual once, confirms an unchanged vector,
  then obtains another exact fresh guard before sending the new target. A changed
  wake vector or lost confirmation prevents the target write. Plain On continues
  to use the existing saved-origin policy.
- Only confirmed, profile-bound Manual-Off memory can supply an Off intensity
  basis. An unknown or Automatic origin cannot reuse retained Off bytes as a
  brightness choice. Explicit colour without a nonzero basis starts at the
  documented 5%; an intensity-only request asks for a colour.
- Pending colour and intensity gestures combine into the latest pending intent.
  Detailed channel, mode and power actions invalidate pending compact intent;
  compact actions invalidate pending detailed sliders. A newer gesture does not
  cancel a transaction that has already begun. Role changes are checked again
  under the coordinator lock before admission.
- The three-second action deadline includes debounce and lock waits. Cancellation
  invalidates the transport epoch before nested I/O can swallow cancellation.
  Every subsequent send checks that epoch. The client retains its lock until the
  child operation settles and the socket closes. Settlement can exceed the
  admission deadline; this is not a claim that already transmitted device bytes
  can be revoked or that an HTTP timeout cancels a HA service.
- Communication failure, contradiction and uncertain output still clear
  readiness, invalidate queued actions and never trigger retry or restoration.
  Setup, polling, option reload, reconnect and unload remain query-only.

## Findings and resolutions

The author first reproduced a Python 3.9 nested `wait_for` cancellation race:
cancellation immediately after the channel write could allow the subsequent
Manual save. The operation now runs as a separately tracked task, with its epoch
revoked before cancellation reaches nested I/O and settlement completed before
the lock is released. A deterministic regression models swallowed inner
cancellation and requires exactly one write, no retained writer/task, and no
subsequent command without a new read.

The independent Python 3.14 run then exposed a logging issue in that repair.
Although all 90 assertions passed, a cancelled `asyncio.shield` reported the
expected epoch rejection to the event-loop exception handler. The final code
shields a non-raising result envelope and explicitly propagates its result or
exception. The deterministic cancellation regression now captures the loop
exception handler and requires no unexpected errors, while preserving the
no-late-write assertions.

The independent native service test also reproduced a usability failure:
intensity-only at a verified all-zero state sent no write but made the entire
device unavailable. Its instruction to choose a colour could not be followed
until a recovery poll. The final dedicated `CompactInputError` carries the fresh
prewrite observation. Client and coordinator revoke older queued requests while
retaining and publishing that observation, without communication backoff. A new
explicit colour request is immediately possible. This exception is raised only
before any output command; uncertain operations retain the previous fail-closed
policy. The native regression failed before this repair and passed afterward
with the real client and loopback lamp, including the immediate colour action.

## Independent native UX and mixer review

The coordinating reviewer reported PASS with no unresolved finding for
`light.py`, `number.py`, `config_flow.py` and the pure `compact.py` mixer. This
separate review confirmed that roles are explicitly versioned, independent of
display labels and disabled when absent or invalid; the existing Light identity
is retained; the optional Intensity Number supplies a literal zero-to-100 range;
zero uses durable Off; input RGB amplitude is applied once; and intensity-only
scales all six current channels rather than reconstructing a colour preview.
The coordinating reviewer also independently ran the 33 pure mixer tests: PASS.

Native service tests cover HA's conversion of brightness percentages and HS
inputs, actual REST state publication, optional entity identity across mapping
enable/disable/re-enable, owner names, label/role independence, and preserved
Off memory during option reload. Four tests run native HA service/HTTP dispatch
through the actual client against a loopback TCP lamp, including the
non-normalized RGB case and intensity-zero/bare-On restoration. These remain
synthetic integration evidence, not physical lamp or dashboard acceptance.

## Frozen inputs

Paths below are relative to the repository root. Hashes were checked before and
after the final independent runs and remained unchanged.

| File | SHA-256 |
| --- | --- |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/client.py` | `a6ff599772f3483be1f930dc1cbfcac4cd2678d3e3023f3ec8112e74c5393432` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/coordinator.py` | `41c6bf3d0e70a7fdba3af54828d1298f74db8fdf671b702f25ed8906ed47f5f3` |
| `tests/test_aquarius_client.py` | `e892d5ed35a9ba39d3b58f17f45bff105225cc79c1dd7a522012535a9eaa8638` |
| `tests/ha_aquarius/test_compact_coordinator.py` | `20951d4f00188ee3d159845ec865f9e0cb21587d4c05902a6066f5dcb0113ca7` |
| `tests/ha_aquarius/test_compact_entities.py` | `2c5f21790d5e0b330f5912fc768afcf369ae06d9237a85cb6c4b02f6718473ee` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/compact.py` | `bc8ebd52b84b91170064704e8aa294b553dcb793ad3003b469831c54df6a433e` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/light.py` | `fb23f6a44318338a29481690aa855b9cf269b436b9d90e4d896add019f001c28` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/number.py` | `4cebb74d30f7be1c690c6c7e9fcc19bbfd3e13da2bd8b7ef89422eed509c4eae` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/config_flow.py` | `c3a21db8ec2a4742d9d0beb637ddea65bbfe2054af4e51cd2e294b6c0f5da4c4` |

## Reproduction

Use isolated Python 3.14.7 environments. The checked-in
`requirements-ha-test.txt` pins HA 2026.9.1 and
`pytest-homeassistant-custom-component==0.13.364`. The second private test
environment changes only those two package pins to HA 2026.9.2 and fixture
0.13.365; repository requirements and CI remain unchanged.

```sh
python -m pytest tests/ha_aquarius -q --disable-socket --allow-unix-socket --timeout=20 --tb=short
python -B -m unittest tests.test_aquarius_protocol tests.test_aquarius_client -q
.venv/bin/ruff check modules/aquarius_plant_led/custom_components/aquarius_plant_led tests/ha_aquarius tests/test_aquarius_client.py
```

Native HA tests block sockets except explicitly marked local loopback simulator
tests and Unix event-loop sockets. The standalone TCP unit tests use only
synthetic local loopback servers. No physical output, colour accuracy, dashboard
touch interaction or installation result is established by this review.

## Final frozen results

| Check | Runtime | Result |
| --- | --- | --- |
| Independent full native HA suite | Python 3.14.7, HA 2026.9.1, fixture 0.13.364 | PASS: 168 tests, 56.92 s |
| Independent full native HA suite | Python 3.14.7, HA 2026.9.2, fixture 0.13.365 | PASS: 168 tests, 57.78 s |
| Independent protocol and client suite | Python 3.14.7 | PASS: 91 tests, 64.452 s, clean output |
| Author protocol and client rerun | Python 3.9.6 | PASS: 91 tests, 66.409 s, clean output |
| Coordinating reviewer pure mixer suite | Python 3.9.6 | PASS: 33 synthetic tests |
| Ruff on integration, native tests and client tests | Repository lint configuration | PASS |

The native environments run on macOS arm64. The test-version comparison changes
only HA and its matching pytest fixture pins; it does not change repository
requirements or CI. This source gate does not authorize additional physical
experiments. The separate reviewed bounded acceptance procedure and current
user authorization govern any actual lamp validation.

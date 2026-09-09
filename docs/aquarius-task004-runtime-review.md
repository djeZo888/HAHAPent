# Task 004 native integration review

Review date: 2026-09-09. Status: **PASS — independent source and synthetic native
HA gate after the storage-envelope and active-poll unload repairs**.
This review covers native integration source and synthetic tests only;
it does not validate an actual lamp, Home Assistant deployment, or camera.
The separately gated software-power allowlist now admits one exact raw profile
after coordinator-authorized device validation. This source review does not
independently substantiate that operational evidence; other profiles stay blocked.

## Scope

The review covers the client, coordinator, private power memory, native setup
and unload, Light, Button, mode-status Sensor, retained Select, and their tests.
The bounded operator procedure has a separate
[Task 004 worker review](aquarius-task004-validation-review.md).

## Frozen source and independent results

Paths in the first nine rows are relative to
`modules/aquarius_plant_led/custom_components/aquarius_plant_led/`.

| File | SHA-256 |
| --- | --- |
| `client.py` | `1e30b6713557c230ea2cc278bc9d4a37460f864fd00dd30e3795f7145d5a61da` |
| `coordinator.py` | `6aea8eb40b896025607e856ba8f807e1112cbee2e734eba36218dbd2681e150a` |
| `state_store.py` | `9b4433e93a56dbddee3e39982997b50e814f4f9d243937f7117067a9c9239a39` |
| `protocol.py` | `427d92e578831029d96fc17552c37652494fb4675302def0ba1912e94e9f378e` |
| `__init__.py` | `59347e13afc30f4eee3e9e2a9bc21aa95bb59859821a732fe794c617fbe3f91e` |
| `light.py` | `0fd99d3bfef04f9603b4684e8db6d3bfdc1124e4a15fec19854a65c542a5de18` |
| `button.py` | `511c699fcea7935d3e859bf890c1c3c13bece785282895b4fff39b7eadcac541` |
| `sensor.py` | `85db395214e42a985631e675470f29039c3c038c716d842151779f75fae7e021` |
| `select.py` | `6b3e5582d4dbb9b856d3a7965a84279ce19c5c0d4e89eb604cc3e3f8e892936c` |
| `tests/ha_aquarius/test_power.py` | `a3eced3fba50153266c3c555c905fea00d69befb64dd908115c2b3527c690d1f` |
| `tests/ha_aquarius/test_power_memory.py` | `0dc4111003c0cb789ca2d337362b4b48db38adc70547c9b2e232ba8fcb0fbcf9` |
| `tests/ha_aquarius/test_runtime_review.py` | `69d050488a8985b1ee85ae256e4c4ad6f2c0155714d69fe4ea80921423920047` |

Using the pinned HA environment described in
[tests/ha_aquarius/README.md](../tests/ha_aquarius/README.md):

```sh
python -B -m pytest tests/ha_aquarius -q --disable-socket --allow-unix-socket --timeout=20
.venv/bin/ruff check modules/aquarius_plant_led/custom_components/aquarius_plant_led tests/ha_aquarius tests/test_aquarius_client.py
```

Independent full native result: **112 tests PASS in 37.55 seconds; Ruff PASS**.
The suite exercises the actual HA 2026.9.1 loader, lifecycle, registries, services,
coordinator, storage, options flow, and entities. Device traffic is synthetic,
with network admission limited to loopback for designated transport tests.
The separate independent client baseline passed **50 tests in 43.407 seconds**;
after the allowlist change, the new exact-profile admission and existing
separate-power-gate tests passed **2 tests in 1.526 seconds**. The tested runtime
and focused regression hashes were checked before and after the final suite.
Changes require the affected review and tests again.

## Reviewed behavior

- Explicit Off first obtains a fresh matching state and durably saves its
  original mode and available nonzero Manual mix. The client reads again after
  persistence before sending Shutdown. Confirmation requires the exact raw
  profile, mode 8, and either the pre-Off vector or an unambiguous all-zero reply.
  The saved Off intent remains pending until device confirmation and a separate
  verified storage write finish.
- Explicit On with trusted Manual-origin memory sends Manual first. If the
  independently read vector already matches the saved mix, no channel command
  is sent. A zero-Off to zero-Manual result permits a saved-vector write only
  after its mode barrier, fresh full read, and another fresh exact Manual-zero
  guard. Unexpected retained-to-zero, mixed-vector, profile, or mode changes
  stop the action without replay. No channel vector is written in Shutdown.
- An Automatic origin, missing or untrusted Manual memory, and explicit Resume
  schedule select the controller's stored Automatic program without inventing
  percentages or uploading a program. Logical On follows raw Manual/Automatic
  mode even when all percentages are zero. Raw Shutdown is Off; unknown modes
  remain unknown. The Light has ON/OFF capability only.
- Setup, polling, reconnect, native reload, options reload, unload, and native
  removal issue no lamp writes. A read may update private HA memory, but that
  memory is acted upon only by a later explicit power service. Existing Number
  and Select unique IDs are unchanged; the Select remains available as an
  advanced configuration entity.
- Per-entry storage is versioned, private, and atomically written. A fresh
  storage reader must observe the new revision and exact candidate after each
  save, since HA's native save can log and swallow a filesystem failure.
  Corrupt or incompatible records block further Off-state persistence and
  remain unchanged. Native removal deletes only the removed entry's own record.
- One coordinator lock and one client lock serialize commands and complete
  read/write/readback transactions. An admitted service has a three-second
  deadline covering debounce, lock waits, persistence, and the client operation.
  Cancellation invalidates epochs and settles the active client before its task
  completes. A file write already dispatched to an executor is also settled
  before releasing the command lock, preventing an older intent from replacing
  a newer one. Waiting for that file operation may outlast the deadline; it
  cannot proceed to a deferred lamp write afterward.
- Unload tracks the entire active polling read and its observation save, cancels
  and settles it along with an active command, and prevents queued polls from
  starting new work while quiescing. A failed-unload recovery read is permitted
  while command admission remains closed. Reload and native removal therefore
  cannot leave an old observation writer behind the replaced entry instance.
- Faults invalidate queued requests. A subsequent successful poll admits new
  explicit actions and does not replay an earlier failed or canceled request.
  No runtime write retry, cleanup watchdog, startup restore, schedule upload,
  or Manager device-control path is introduced.

## Findings

HA's storage version comparisons use equality, allowing JSON boolean or float
version values to compare equal to integer version 1. The initial power-memory
preflight checked envelope shape but did not reject these malformed version
types. The implementation author added strict integer version checks before HA
Store loads the record, plus actual-file boolean/float version preservation
regressions. Source inspection and the final native suite confirm that repair.

A second independent regression reproduced a lifecycle race: an explicit
coordinator refresh could still be awaiting an observation storage write when
native reload completed. That stale writer could then replace a newer
coordinator's saved power intent. Native DataUpdateCoordinator shutdown only
unschedules future calls; it does not settle every caller-owned active refresh.
`tests/ha_aquarius/test_runtime_review.py` failed against the candidate in
0.17 seconds because reload completed while the old observation save remained
paused. The implementation author added tracked poll cancellation and settlement
before native unload; both reload and native Delete variants pass in the
independent final suite. The initial failure is retained here as review history.

## Evidence limits

A native HA test uses the actual framework and services
with synthetic controller transport; it is not an actual-lamp test. Selected
storage tests use real HA serialization and atomic filesystem writes inside
per-test temporary directories, while other lifecycle tests use HA's storage
fixture. The three-second action deadline does not bound HTTP admission before
the service handler runs, undo transmitted bytes, or guarantee physical
restoration after network or host loss.

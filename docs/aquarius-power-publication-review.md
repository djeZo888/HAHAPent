# Power-origin state publication review

Review date: 2026-09-09. Status: **PASS — independent source and native HA
fixture gate for the 0.3.1 publication fix**. This does not establish actual
Automatic-origin On acceptance. The published 0.3.0 candidate remains immutable,
and its failed Automatic01 attempt remains a failed experiment.

## Cause and resulting behavior

The coordinator reported that Automatic01 completed native Resume and Off,
independently read mode 8 with six zeros, then rejected the Light's saved-origin
attribute. On was never sent. Exact original Manual recovery completed within
the declared bound. The validation worker correctly refused to treat the
missing-memory fallback as proof of a saved Automatic origin.

Source review identified the ordering error: `async_turn_off` published the
confirmed device state while `off_origin` was still an unconfirmed pending
record. The Light therefore published its fallback `on_behavior`. The later
durable origin confirmation changed memory without notifying entity listeners.
An unchanged-state poll can suppress listener updates, so another poll need not
repair the cached attribute.

The author reproduced this through the actual HA 2026.9.1 REST service and state
views, with the actual integration client and a synthetic loopback lamp. Both
Automatic and Manual origins failed the immediate attribute assertion while the
internal confirmed memory was correct: **2 failing cases in 2.97 seconds**. This
red run is author evidence; the independent reviewer verified the source
mechanism and the corrected behavior below.

Version 0.3.1 publishes Off from `finally` after confirmation storage settles.
Successful publication therefore sees the confirmed origin; a failed save still
publishes the known physical Off state with the safe fallback. Cancellation
settles the pending storage operation, publishes the known device state, then
the enclosing command window marks the action unavailable. No command is
retried. Channel, mode, and On actions similarly settle their observation memory
before publishing memory-dependent attributes, so invalidated origins disappear
from the same service's resulting HA state.

The pinned HA `async_set_updated_data` method always notifies listeners;
equal-state suppression applies to polling, not this explicit publication
method. The fix does not require a new lamp read or write, an extra service call,
or a weaker validation check.

## Frozen source and independent evidence

| File | SHA-256 |
| --- | --- |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/coordinator.py` | `ee304ee534508484a2d3a82b74b590d5ea87004b04375419514d6ce65f20ea25` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/const.py` | `c70c03fca239b145c56c94aa0b77ccc1812826bbea9cb05fd6e071ebf44be78b` |
| `modules/aquarius_plant_led/custom_components/aquarius_plant_led/manifest.json` | `dd08534d47c297ffb02ef93ae427e43d70d9c575a520b7f4c038305128d4cdf7` |
| `tests/ha_aquarius/test_power.py` | `1b4c6878e8b774afe4f7debde5b8abc2a57423fbfcf3a63331faa1d2a1c856b6` |

Using the existing pinned Python/HA fixture environment, the independent command
was:

```sh
python -m pytest tests/ha_aquarius/test_power.py tests/ha_aquarius/test_entities_coordinator.py -q --disable-socket --allow-unix-socket --timeout=20 --tb=short
```

Independent result: **56 tests PASS in 36.72 seconds; Ruff PASS** for the changed
Python source and power tests. The author also reported **20 affected native
power tests PASS in 34.48 seconds** and **117 full native HA tests PASS in 46.59
seconds**. The independent run does not claim to repeat that complete suite.
All four reviewed hashes matched before and after the independent run.

The new REST regression performs actual HA service POSTs and immediate Light
state GETs for both origins, without an intervening poll or reload. It checks
the exact confirmed saved-origin attribute after Off, and the cleared-origin
fallback after On. Additional cases verify Resume invalidation, confirmation
save failure, and cancellation while confirmation storage is pending. The
failure/cancellation cases assert known Off state, unavailable-then-read recovery
where applicable, and no extra lamp commands. The wider independent coordinator
suite covers explicit services, availability, deadlines, queued actions, and
lifecycle cancellation with synthetic device state.

The Automatic composite remains frozen at source hash
`a676683e9bf90033c3e9b8ed60b647d806ffb0432f43ba31db158b707db2d4db`
and test hash
`1c4cb9f5fc0c29eb3b4e8a0dd5ae5898084d7b4ae76b13f1cfd8a6ae1f55699e`.
Its strict saved-Automatic attribute comparison, fresh phase guards, UNKNOWN
no-replay rule, and reviewed deadlines are unchanged.

No unresolved source blocker remains. No live HA, lamp, protected configuration,
credentials, or private evidence was accessed during this independent review.
Only this new review document was edited. Publication, installation through the
existing module workflow, and a new bounded actual Automatic-origin validation
remain coordinator work and require their own recorded results.

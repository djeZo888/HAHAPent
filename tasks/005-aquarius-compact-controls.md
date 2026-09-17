# Task 005 — Optional compact Aquarius colour and intensity controls

Status: **IN PROGRESS**. The owner explicitly requested implementation of a
compact colour-picker/intensity view while retaining the detailed six-channel
view. This follows delivered immutable 0.3.2 at main
`184542a3ec810e93e1a6e52eba36aee2b75fdbd5`; that working release, its visual
acceptance and all historical Task 004 evidence remain intact. Work proceeds on
`codex/aquarius-compact-colour`, targeting independently versioned module 0.4.0.

## Behavior and design

Reuse the existing native Light identity. An explicit, versioned per-lamp map
assigns channels to red, green, blue, white or unused roles. Display labels stay
independent; changing a name never changes control meaning. Missing, malformed
or future-version mapping keeps the original On/Off-only capability. RGB is an
approximation, not spectral calibration. Ambiguous red-family channels may share
the red role without claiming which is ruby. No optical remapping is required.

An explicit colour creates one bounded six-channel recipe, extracting the shared
white component when white channels are assigned. Duplicate roles receive equal
percentages. Brightness-only scales the fresh full six-channel vector directly,
preserving arbitrary detailed mixes up to integer quantization. Intensity means
the strongest channel percentage, not measured luminosity. RGB readback is an
approximation derived from confirmed output; no background task replays a colour.
Colour-only preserves a current nonzero intensity or trusted Manual-Off intensity;
when neither exists, the explicit colour request starts at a documented 5%.
Brightness-only with no trustworthy nonzero mix requires choosing a colour first.
Non-normalized RGB input retains its intensity component; black requests Off.

Zero intensity uses the existing durable software-Off path. Plain On retains
saved Manual/Automatic origin behavior. A new explicit colour/intensity action
from Off is separate from saved-state restoration: it requires guarded Manual
wake, independent confirmation, another fresh exact guard, and one verified
full-vector transaction. Unknown completion or contradictory readback never
permits write replay. All requests keep the existing three-second command bound.

Home Assistant's native Light brightness slider starts at 1%. To provide the
requested literal 0–100% slider, the compact view adds a native Intensity Number
when mapping is configured. The Light's native More-info dialog supplies the
colour picker. The existing six sliders remain in the detailed view. No custom
frontend or Manager redesign is needed.

## Validation and operational scope

Synthetic mixer, client, concurrency, native HA and worker failure tests and
independent review precede any new physical action. Only the coordinator deploys,
configures, publishes or operates test-dev. Use a fresh encrypted backup and
startup/KNX gate before the update and necessary Core restart. Preserve all
existing identities, user configuration, dashboards and immutable releases.

The new reviewed acceptance procedure starts only from freshly confirmed
Automatic mode with modest output. Its targets are at most 5% per channel.
Separate single-action probes retain a ten-second maximum and 9.5-second cleanup
deadline. Multi-action compact probes have a six-second experiment phase,
19.5-second cleanup deadline and twenty-second maximum, with no deliberate hold.
They exercise colour, proportional intensity, zero-Off and explicit colour from
Off. These are new scoped procedures for the requested feature; they do not
reuse authority or unchanged recovery logic from historical experiments.

Only a fresh exact state owned by this probe can admit one Automatic-only cleanup
command. Never restore historical Manual output or replay a percentage snapshot.
Unknown HTTP completion, competing changes or contradictory replies permanently
prohibit further writes in that run. The worker must be detached on the existing
HA-side execution path with local monotonic deadlines and signal-safe cleanup.
Failure pauses new experiments while safe investigation and repair continue.
Independent read-only confirmations follow recovery. No schedule upload, camera
configuration, other-device control, production or network/security change is in
scope. Actual live results will be recorded separately from synthetic tests.

## Source and synthetic acceptance

The [runtime review](../docs/aquarius-compact-runtime-review.md) records the
transport/coordinator review and separate entity/options/mixer review. Offline
testing exposed a Python 3.9 cancellation race, its Python 3.14 shield logging
issue, and an input-error path that unnecessarily made the lamp unavailable.
All were repaired before deployment. No failed physical experiment is implied
by those synthetic findings.

Final source checks: 571 synthetic unit tests PASS on Python 3.9.6; 168 native
framework tests PASS on each of HA 2026.9.1 and 2026.9.2 / Python 3.14.7.
The affected protocol/client suite separately passed 91 tests on both Python
3.9 and 3.14, including the repaired cancellation and input-error regressions.
Ruff, catalog validation, bundle consistency, whitespace and privacy checks pass.

The new [worker review](../docs/aquarius-compact-worker-review.md) freezes the
exact procedure and dependencies. Its author and coordinating reviewer each
passed 37 failure/loopback tests. The pure mixer has 33 passing tests, including
all integer intensity values, rounding, duplicate/unused roles, invalid options
and approximate display behavior. No colour claim is based on simulation.

At the source checkpoint, publication and actual acceptance remained NOT_TESTED.

## Immutable publication

Source commit `d24d1d2b9a024cfc53abd50ba16bcd8fd2593f6b` passed completed hosted
CI run `35224973791`, including Python 3.9/3.13 unit jobs, native HA tests and the
device-free App runtime job. Two builds of that committed tree produced the same
17-file ZIP, SHA-256
`ba04d57b39892974c3976af766ac1714225e688239c681ab797e9286df7dc742`.
The immutable [0.4.0 candidate release](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.4.0)
contains the ZIP, one-row catalog, artifact metadata and checksums. All four public
unauthenticated downloads matched local bytes, and the tag resolves to the exact
source commit. The canonical and bundled catalogs append 0.4.0 without changing
prior releases. Catalog validation and bundle consistency pass.

Test-dev installation, bounded lamp tests and final browser/lifecycle acceptance
remain **NOT_TESTED** at this publication checkpoint.

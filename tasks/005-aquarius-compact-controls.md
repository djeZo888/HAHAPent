# Task 005 — Optional compact Aquarius colour and intensity controls

Status: **DELIVERED — 0.4.0 installed and configured for owner review**.
The owner explicitly requested implementation of a
compact colour-picker/intensity view while retaining the detailed six-channel
view. This follows delivered immutable 0.3.2 at main
`184542a3ec810e93e1a6e52eba36aee2b75fdbd5`; that working release, its visual
acceptance and all historical Task 004 evidence remain intact. Work proceeds on
`codex/aquarius-compact-colour`, delivering independently versioned module 0.4.0;
the final acceptance record uses `codex/aquarius-compact-delivery`.

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

At that publication checkpoint, actual acceptance remained NOT_TESTED.

Catalog PR #16 merged as `72e92f3bffe6125090a034429029d33bf2fba586` after
completed push CI `35225683605` and PR CI `35225688682`; main CI `35226160312`
also passed. The final acceptance metadata promotes the existing release and
canonical catalog without replacing its source tag or four immutable assets.
All prior release IDs, targets and assets are preserved.

## Actual test-dev update and configuration

PASS: a fresh encrypted backup covering HA configuration/database and the
existing Manager/Terminal Apps was downloaded privately. All three encrypted
archive members decrypted and their content was readable. A live full restore
was **NOT_TESTED**. Fresh startup/KNX checks passed before update and restart.

Actual Manager 0.1.2 Refresh/Update installed 0.4.0 through the normal catalog.
All 17 installed source files exactly match the public ZIP. Core configuration
check and one gated Core restart passed on HA 2026.9.2. Before compact setup,
the original 15 available entities, entry/device identities, names and options
were unchanged. No App rebuild was required.

Native options setup enabled the versioned semantic roles using the existing
private optical evidence. Display labels remained unchanged; the ambiguous
red-family pair remains unresolved as red versus ruby. No new optical mapping
or camera access occurred. The native options reload created only the optional
Intensity Number, giving 16 available entities and RGB capability on the existing
Light. The original channel identities and owner-assigned names are preserved.

The existing dashboard path now has a Detailed tab with unchanged cards and a
Compact tab containing Colour and Intensity Tiles. Other dashboard configuration
and metadata are preserved. Native options and a subsequent explicit integration
reload passed; both views, roles, labels and identities survived. Final installed
bytes still match the immutable artifact. Manager remains running and KNX is
connected, with its configuration and other devices preserved.

## Actual bounded lamp acceptance

The frozen worker and dependencies were transferred to the existing private
HA-side runtime and their hashes matched the independent review. Entity ownership
was verified against the same entry/device, and all three private configurations
passed parse-only validation without token or network use.

The private detached launcher also received independent review. Offline tests
reproduced assertion gates being bypassed by optimized Python, dangling output
symlinks, and missing atomic pre-spawn claims. Explicit validation and a no-follow,
exclusive, fsynced claim repaired these before any live probe. Nine launcher
tests and two query-only tests passed. Tokens entered child memory through stdin;
uncertain launches retained their claim and could not be replayed.

Each actual run started from freshly confirmed modest Automatic output. No
historical Manual snapshot was restored. Expectations were calculated separately
from the production mixer, and successful native HTTP completion was followed by
independent complete TCP readback and native mode status.

| Actual procedure | Native actions confirmed | Experiment | Automatic recovery | Total excursion |
| --- | ---: | --- | --- | ---: |
| Colour with explicit modest intensity | 1 | PASS | PASS | 2.755510 s |
| Colour, proportional Intensity increase, literal zero-Off | 3 | PASS | PASS | 6.723512 s |
| Automatic-origin zero-Off, then new colour without an intensity parameter | 2 | PASS | PASS | 5.717631 s |

The single-action run stayed within ten seconds; the two composites stayed
within twenty seconds, including confirmed cleanup. The final case exercised
guarded Manual wake and the documented modest colour-only fallback. Three fresh
HA-side read-only confirmations followed each cleanup. Query-only native refresh
confirmed all 16 entities available and Following schedule. A final native reload
and three further independent reads also passed. **No actual experiment failed.**

These results establish the tested native control paths and readback, not optical
colour accuracy. No schedule, clock, preset, firmware, mains switch, KNX device,
camera setting, network/security setting or production system was changed.

## Actual browser acceptance and remaining limits

Both tabs are present in the real installed dashboard. All six detailed titles
have equal rendered and scroll widths: 238 pixels at desktop, 308 pixels at a
390-pixel viewport. Screenshots included the lower channels after scrolling.
Colour and Intensity also fit at narrow width; the native slider exposes minimum
0 and maximum 100. The native Color wheel renders at desktop and phone width.
Opening Colour initially shows HA's brightness control; select its Color wheel
button to display the picker. The temporary viewport override was reset and the
working Compact view was left open for the owner.

Browser navigation/rendering is **PASS**. Actual iPhone touch/drag, browser output
gestures, calibrated colour accuracy and full backup restore remain **NOT_TESTED**.
Bounded lamp actions used the reviewed HA-side native service procedure, not
uncontrolled browser gestures. Pure mixing tests, native framework simulations,
hosted CI and actual lamp results above are distinct evidence. Private targets,
role evidence, captures, raw reports and credentials remain outside Git.

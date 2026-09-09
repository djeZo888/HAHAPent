# Task 004 — Aquarius Plant LED UX, optical labels and software power

Status: **IN PROGRESS**. This improves the existing integration and its installed
configuration. The owner supplied the private assignment and camera share;
neither the original attachment nor private target/capture data belongs in Git.

## Baseline and scope

Task 003 completed at main `cbe8d2f6c9a2ec4c04564da3230cf4cae2e08a24`.
Its final main CI [completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34293970401).
The new branch is `task/004-aquarius-ux`. Protected API and pinned SSH access
passed read-only checks; current HA is 2026.9.1. Existing Manager 0.1.2 and module
0.2.0 are the working baseline. Historical Task 003 failures, successful tests,
and immutable releases are retained.

Required delivery: Following schedule / Manual override status and Resume
schedule; six stable channel identities with configurable evidence-backed labels;
an ON/OFF-only native Light with versioned origin/manual-mix memory; native Tile
sliders that avoid ordinary More-info navigation; immutable module update,
actual lamp/lifecycle acceptance, and final configured owner demonstration.
Shutdown support stays separately gated until bounded hardware readback passes.
Unknown restoration origin on explicit On resumes the existing stored schedule;
no full-brightness vector is invented. Startup and background paths never write.

## Initial safety and evidence plan

- Reuse the detached HA-side worker's monotonic deadlines and guarded cleanup.
  Optical sampling begins at one-channel deltas no greater than five points,
  selected output at most 20%, and at most ten seconds including restoration.
- Compare multiple private camera frames; report ambiguous whites/reds as
  configurable pairs, never as guessed mappings. Do not infer PWM frequency.
- Preserve the observed starting mode in shutdown validation. The current stable
  Manual baseline requires Manual-first recovery. Only observed Shutdown-zero
  followed by confirmed Manual-zero and a fresh exact guard may admit one
  deliberate saved-vector restoration. Retained Off output followed by changed
  Manual output is contradictory and prohibits replay. Automatic-origin recovery
  sends only Automatic. Each path requires offline tests and independent review.
- Read-only observation may characterize normal schedule progression; no
  schedule/preset/effect/clock upload or editing is authorized.
- Use the existing backup/startup/KNX gate before deployment/Core restart.
  Preserve entry/entity identities, other dashboards, global Recorder settings,
  KNX, other devices, camera configuration, network/security and production.

## Current checks

| Check | Status | Evidence |
| --- | --- | --- |
| Completed committed baseline | PASS | Main and completed CI verified |
| Protected HA/SSH access | PASS | Existing token/key/host pin reused; no write probe |
| Native computer/iPhone surface discovery | BLOCKED currently | Computer Use reports the Mac locked; unlock requested while safe work continues |
| Private camera read-only access | PASS | Guest-scoped stream decoded; multiple frames show the LED board; no camera settings changed |
| Optical colour mapping | NOT_TESTED | Bounded worker under offline review; no colour labels guessed |
| Direct Manual-origin software Shutdown | PASS | Mode 8 readback all-zero; Manual-first guarded saved-vector restoration and three later reads match original state; 2.746025 s |
| Camera software-Off observation | PASS | Multiple private frames show darkness and restored lighting; no camera settings changed |
| Native HA power and Automatic-origin return | NOT_TESTED | Runtime/HA adapter acceptance remains pending |

The initial Task 004 checkpoint `beda55630fbcf743a26affccb73838cf15d15902`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34338192756).
A fresh encrypted backup was downloaded privately; isolated decryption and
selected configuration readability passed. A full live restore was not tested.
Current installed baseline retains one configuration entry/device and twelve
available entities. Actual read-only samples show stable Manual output, which
is preserved; they do not establish Automatic interpolation. The camera viewing
path now works through guest-scoped MQTT/WebRTC streaming with TLS verification.
No camera configuration was changed.

## Actual direct Shutdown evidence

The reviewed direct-worker checkpoint `072670dd49127628344caf5467ba6730474d0767`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34339505146).
The first launch was rejected during setup because the private report path was
relative. No worker transaction or lamp command began. The coordinator corrected
the launcher to use absolute paths and passed an HA-side configuration/report
check with zero lamp network operations; reviewed worker bytes were unchanged.

The following Manual-origin test passed its experiment and recovery in
**2.746025 seconds**. The lamp reported Shutdown with all six exposed channels
zero. Manual alone still reported zero, so the worker used the independently
reviewed fresh-zero guard and one deliberate original-vector-plus-Manual restore.
The final exact Manual mode/vector matched the baseline. Three later independent
read-only samples confirmed the same state. Multiple camera frames showed actual
darkness and return of the prior lighting. This is actual device/optical evidence,
separate from offline tests, and admits only the exact validated raw power profile.
Automatic-origin power, versioned HA memory and native service acceptance remain
pending. Current lamp percentages and all captures remain private.

The existing native entry was temporarily disabled through HA during direct TCP
experiments to release its polling connection. Its identity/configuration were
preserved; the final installation must be re-enabled and configured. No Core
restart, other integration change or network/security change was needed for this
pause. The earlier detached read-only observer completed before testing.

## Immutable UX candidate and native acceptance gate

Source checkpoint `bbb4b5385944ac9bd98f25086f9e0de62bcb1692` passed
[completed CI](https://github.com/djeZo888/HAHAPent/actions/runs/34340988349).
The immutable [0.3.0 candidate](https://github.com/djeZo888/HAHAPent/releases/tag/aquarius-plant-led-v0.3.0)
was published from that exact source. Public unauthenticated downloads matched
all locally built assets, and Manager archive validation passed. The ZIP SHA-256
is `02973dfe98d440e999769c6c550f5ae53e95765b6d02ff8b31d4c47ab8071fac`.
Existing releases are retained. Actual updated-module acceptance remains pending.

The native HA service worker passed 29 independent synthetic/loopback tests,
including unknown HTTP completion and exclusive TCP handling. Its frozen hashes
and operational conditions are in the
[native acceptance review](../docs/aquarius-task004-ha-validation-review.md).
These are separate from actual native HA/lamp tests.

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
| Shutdown hardware behavior | NOT_TESTED | New bounded worker/recovery design under offline review |

The initial Task 004 checkpoint `beda55630fbcf743a26affccb73838cf15d15902`
was pushed and [CI completed successfully](https://github.com/djeZo888/HAHAPent/actions/runs/34338192756).
A fresh encrypted backup was downloaded privately; isolated decryption and
selected configuration readability passed. A full live restore was not tested.
Current installed baseline retains one configuration entry/device and twelve
available entities. Actual read-only samples show stable Manual output, which
is preserved; they do not establish Automatic interpolation. The camera viewing
path now works through guest-scoped MQTT/WebRTC streaming with TLS verification.
No camera configuration was changed.

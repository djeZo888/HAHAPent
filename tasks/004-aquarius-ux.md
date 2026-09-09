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
- Begin shutdown validation from stable Automatic. Query mode/channel behavior,
  then deliberately restore Automatic without replaying a stale channel vector.
  Admit Manual-origin power tests only after response/retention semantics and
  recovery have passed offline tests and independent review.
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
| Camera observations and colour mapping | NOT_TESTED | Private optical access and capture procedure under investigation |
| Shutdown hardware behavior | NOT_TESTED | New bounded worker/recovery design under offline review |

# Task 003 — Aquarius Plant LED

Status: **IN PROGRESS**. This task follows the owner's revision-2 assignment;
the original package, device configuration and packet evidence are private.

## Baseline and authorization

Task 002 is complete at main commit `3ce396c27296e33473dbbbeebe68bff034d8203d`.
The fetched remote matched the clean checkout; the final
[CI run](https://github.com/djeZo888/HAHAPent/actions/runs/34280044358)
completed successfully. The private completion record agrees, and no Task 002
operator process was active. Work began on `task/003-aquarius-plant-led`.
Manager 0.1.1 is the existing completed implementation, not a new deliverable.

The owner authorizes HA-side read-only protocol diagnostics, independently
versioned module implementation/publication, the actual Manager/native HA
lifecycle, and bounded reversible tests of the selected lamp. Initial tests may
change one channel by at most five percentage points for at most ten seconds,
followed by deliberate restoration. Unexpected changes or a competing controller
stop writes. Core restarts require a fresh encrypted, privately downloaded and
readable backup plus the startup/KNX safety gate. Other devices, provisioning,
network policy, infrastructure and production remain outside scope.

## Current evidence

| Check | Result | Scope |
| --- | --- | --- |
| Package integrity/private placement | PASS | Supplied checksums verified; installation settings outside Git |
| Protected API/SSH access | PASS | Existing profile, credentials, key and host pin reused; no write probe |
| Supplied reference tests | PASS | 21 offline/synthetic methods, including loopback TCP; not lamp evidence |
| HA-side protocol reads | PASS | Meaningful system reply and six valid percentages; no lamp writes |
| Initial SSH forwarding attempt | FAIL | Connection reset; forwarding ended without SSH configuration changes |
| Supplied probe against channel response | FAIL | Probe required E2 FC, while the queried lamp returned E2 FA |
| Adapted read-only probe | PASS | Existing HA-side netcat transport; two queries, explicit E2 FA acceptance |
| Bounded lamp writes | NOT_TESTED | Awaiting reviewed client and restoration procedure |
| Native HA and Manager lifecycle | NOT_TESTED | Awaiting tested module and deployment gate |
| Optical colour mapping | NOT_TESTED | A–F retained; no inferred wavelength mapping |

The supplied app-static evidence establishes raw TCP frame constructors and
the controller-specific C/D permutation. It does not establish firmware behavior.
Actual readback identified controller bytes `(28, 30)`, raw version bytes
`(26, 29)`, and channel-count byte `6`; the documented swapped controller flag
does not match. These are raw fields, not an invented firmware name or stable
hardware serial. Raw frames and actual settings remain private.

## Distribution constraint under review

Manager 0.1.1 reads its built-in catalog from the installed App's bundled file.
Its refresh action downloads extra-source metadata, but does not download the
built-in catalog. Adding the same repository as an extra source fails the
source-identity guard. Publishing the new root catalog alone therefore cannot
make this module appear in the installed Manager. Rebuilding the Manager is
excluded by this assignment. Do not bypass ownership, directly copy acceptance
code, edit App internals, or weaken source identity to conceal this constraint.
The concrete deployment decision will be recorded once the module is reviewable.

## Intended scope

Native host/port setup and reconfiguration; one device with six A–F percentage
Numbers; fresh serialized read-modify-write and confirmed manual operation;
explicit return to automatic program; diagnostic unknown modes; read-only setup,
polling, reconnect and reload; independently versioned pure-Python module.
Schedules, effects, clock/temperature claims, provisioning, firmware changes,
Shelly control, calibrated optical output and RGB colour-wheel control are excluded.

Completion requires separately reported synthetic tests, device readback,
physical observations and actual HAHAPent/native HA lifecycle evidence.

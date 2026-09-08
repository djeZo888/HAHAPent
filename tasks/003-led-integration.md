# Task 003 — Aquarius Plant LED

Status: **BLOCKED — hardware control and installed catalog delivery**.
This task follows the owner's revision-2 assignment;
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
| Initial bounded channel test | FAIL | One-point Channel A change reached Manual; immediate reconnect verification failed and restoration exceeded ten seconds |
| Deliberate restoration | PASS | Fresh state matched the commanded change; all original channel values and Automatic mode were subsequently restored and read back |
| Further lamp controls | BLOCKED | Stopped after unexpected behavior; no public write-enabled controller profiles |
| Native HA on protected test-dev | NOT_TESTED | Candidate not installed; real HA framework tests use synthetic fixtures |
| Actual Manager installation/lifecycle | BLOCKED | Installed App cannot load a new built-in catalog without an App update |
| Encrypted deployment backup / Core restart | NOT_REQUIRED | No HA deployment or Core restart occurred |
| Optical colour mapping | NOT_TESTED | A–F retained; no inferred wavelength mapping |
| Repository synthetic suite | PASS | 258 tests on Python 3.9.6, including 51 protocol/client and 12 packaging tests |
| Native HA framework suite | PASS | 38 tests on Python 3.14.7 / HA 2026.9.1, including two actual-client loopback cases |
| Current test-dev health | PASS | Core running, KNX entries loaded, Manager 0.1.1 started and protected; no deployment/restart |

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
The smallest exception is a versioned App packaging update containing the new
catalog while leaving Manager logic unchanged. A durable alternative is an
explicitly authorized built-in remote-catalog refresh feature. Neither has been
implemented or deployed under the current no-rebuild constraint.

## Failed bounded control and recovery

The reviewed client passed two stable, read-only refreshes. The first test sent
only a one-percentage-point Channel A reduction and the app-derived Manual
command. The immediate fresh-connection readback failed; a later read confirmed
the exact changed channel set and Manual mode. The harness stopped without
automatically overwriting an unknown state, but its initial failure path did not
complete restoration inside ten seconds. This is a failed safeguard outcome,
not a successful bounded control test.

A separate, guarded recovery first required fresh state to equal the known test
result. It restored the original six values, but Automatic mode did not apply
in that sequence. A subsequent mode-only recovery kept its connection open for
a bounded response and then independently read the original values and Automatic
mode. Recovery passed. There was no channel sweep, shutdown, schedule write,
Shelly action or further control testing.

The exact cause of immediate reconnect failure and command-sequence behavior is
unresolved. HA-side SSH/netcat transport lifetime, controller timing, and actual
firmware behavior must be distinguished with read-only investigation before a
revised bounded plan. Do not silently add command retries or claim a timing fix.
The public candidate keeps its write-profile allowlist empty, so no production
control path can write to this or any other controller.

Native setup describes the read-only candidate. Six Number values remain
available; channel/mode actions fail explicitly as unvalidated before calling the
client. A Write support diagnostic distinguishes this state from a network outage.

Resume requires a reviewed restoration procedure that handles an uncertain
command within the bounded window and does not overwrite competing changes;
successful small-change/readback/restoration tests for all six channels;
and an authorized path to deliver catalog metadata to the installed Manager.
Actual setup, update/rollback/removal, Manager-off operation and Mac-off operation
remain NOT_TESTED. No optical or calibrated output claim follows from byte reads.

## Intended scope

Native host/port setup and reconfiguration; one device with six A–F percentage
Numbers; fresh serialized read-modify-write and confirmed manual operation;
explicit return to automatic program; diagnostic unknown modes; read-only setup,
polling, reconnect and reload; independently versioned pure-Python module.
Schedules, effects, clock/temperature claims, provisioning, firmware changes,
Shelly control, calibrated optical output and RGB colour-wheel control are excluded.

Completion requires separately reported synthetic tests, device readback,
physical observations and actual HAHAPent/native HA lifecycle evidence.

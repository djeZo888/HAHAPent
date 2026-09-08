# Aquarius Plant LED

**0.1.1 is an interim read-only recovery-fix prerelease.** It adds a queried
mode/profile response before closing a write connection and handles changing
Automatic-program channel levels during explicit actions. These control-path
changes have synthetic coverage; the shipped controller write allowlist remains
empty. This candidate supports read-only installation, update, rollback and
removal checks while bounded hardware validation is repaired. Working controls
require a later independently validated release.

The immutable **0.1.0** candidate and its incident evidence remain historical.
Its first bounded control test failed during immediate reconnect verification,
and restoration exceeded the ten-second limit. The original channels and
Automatic mode were subsequently restored and confirmed. The earlier SSH
transport's connection lifetime is not evidence that native TCP or the lamp is
incompatible; the continuation separates transport diagnosis from hardware
claims. Neither read-only candidate completes the working-control assignment.

Local Home Assistant integration targeting the Aqua Medic Aquarius Plant Plus 60.
The independently versioned module uses raw TCP and needs no cloud account,
MQTT, Manager process or developer computer at runtime. Release acceptance is
recorded in [Task 003](../../tasks/003-led-integration.md).

## Installation and setup

Install the published **Aquarius Plant LED** candidate from HAHAPent's catalog,
then follow **Configure in HA** to add the native integration. Enter the lamp's
already provisioned IP address or hostname and TCP port (default `8080`). The
connection originates from Home Assistant. Setup sends only system/channel reads.
Follow the Manager's Core restart indication after changing integration code.
Back up HA and review startup effects before restarting an existing installation.

Manager 0.1.2 adds canonical built-in catalog refresh, retaining validated cached
metadata across App restarts. Use **Refresh** to discover newly published module
versions after that Manager update is installed. The older Manager 0.1.1 only
bundles its built-in catalog, so update it through the supported App-store path
first. Do not copy integration files over Manager ownership or add the same
repository as an extra source. The task report records actual installed versions
and lifecycle results separately from these instructions.

One device contains six **Channel A–F** percentage sliders, an **Operating mode**
selector, a **Write support** diagnostic and raw protocol diagnostics. Each slider
displays integer `0–100%` values. Commands return an explicit read-only validation
error in this candidate; another poll cannot enable an unvalidated profile.
For a future validated profile, the implemented and synthetically tested behavior
enters and saves **Manual**, pausing the stored automatic program. Other channels
are preserved from fresh readback. **Automatic program** explicitly resumes the
existing schedule. This action does not edit that schedule or restore a previous
manual mix.

Channel letters describe protocol order, not verified colours or wavelengths.
Rename entities in Home Assistant after identifying them; names do not determine
their stable IDs. Use the native entry's **Reconfigure** action when the same
lamp's address changes. Identity is local to the HA config entry, since no verified
immutable serial number is available. Replacing the lamp at the same address
cannot be reliably detected from these protocol fields alone.

## Behavior and limits

- Startup, setup, polling, reload and reconnection only read state. No brightness,
  mode, schedule, clock or saved state is replayed automatically.
- Polling starts at 30 seconds and backs off to 5 minutes during failures.
  Explicit slider changes are debounced. A future enabled profile must match the
  freshly read mode and profile. Changes to Manual output are a conflict;
  schedule-driven level changes while the same Automatic mode remains active are
  allowed only for an explicit action, preserving the other five fresh values.
  The write connection remains open for a queried mode/profile confirmation,
  followed by a fresh connection for channel readback. An acknowledgement or
  echoed command cannot confirm the change.
- Each admitted explicit action has a three-second deadline including debounce
  and waiting for communication locks. Expiry cancels and settles the client
  transaction, marks output unavailable and prevents queued work from replaying.
  This does not bound HTTP service admission or recall bytes already sent to the
  controller. A fresh read is required before another deliberate action.
- An unavailable lamp stays unavailable, including when another device cuts mains
  power. This integration never controls a Shelly or restores mains power.
- A changed or unconfirmed state stops that action; no write retry loop runs.
  Wait for a successful read, review the actual state, then make a new deliberate
  change. Close competing controller apps when commissioning.
- Only explicitly validated controller/version/count profiles permit writes.
  Unknown profiles and unknown modes remain diagnostic rather than being treated
  as off. Raw version bytes are not a manufacturer firmware version string.
- Shutdown/on-off, master brightness, RGB colour wheels, effects, schedule/clock
  writes, temperature, provisioning, factory reset and firmware updates are not
  exposed. Six percentage values are not calibrated light-output measurements.

## Dashboard example

Replace these example entity IDs with those created in your installation:

```yaml
type: entities
title: Aquarium channels
entities:
  - entity: select.aquarius_plant_led_operating_mode
  - entity: number.aquarius_plant_led_channel_a
  - entity: number.aquarius_plant_led_channel_b
  - entity: number.aquarius_plant_led_channel_c
  - entity: number.aquarius_plant_led_channel_d
  - entity: number.aquarius_plant_led_channel_e
  - entity: number.aquarius_plant_led_channel_f
```

## Troubleshooting and recovery

For connection failures, check the configured target and the route from HA to its
TCP port. A successful TCP connection alone does not prove protocol compatibility.
Do not reprovision a working lamp or enable broadcast discovery. Unsupported data
must be investigated privately; do not post configuration, addresses or captures.

For a conflict or unconfirmed change, inspect the current state and other active
controllers. No automatic restoration is attempted because it could overwrite a
newer intentional change. Never infer software shutdown from an outage.

Use HAHAPent's owned-code rollback to restore a prior module release. Rollback
changes integration files, not lamp settings or schedules. Native config entries
must be deleted through HA before Manager uninstall; code removal never edits
HA storage manually. Refer to the [test-dev recovery runbook](../../docs/test-dev-runbook.md).

## Evidence and licensing

Protocol behavior was derived from supplied AMled 1.6.1 static evidence; no vendor
Java, bytecode, original app package or device capture is distributed. Original
reference scaffolding informed this independent Python implementation. License
selection remains pending; no upstream app license is asserted for this project.

Synthetic protocol/TCP tests and real HA framework tests use manufactured data.
The task report separately records actual device readback, bounded control tests,
HA deployment and observations. Physical colours and optical output remain
unverified until independently observed.

Platform references: [HA config flows](https://developers.home-assistant.io/docs/core/integration/config_flow/),
[Number entities](https://developers.home-assistant.io/docs/core/entity/number/),
and [coordinated fetching](https://developers.home-assistant.io/docs/integration_fetching_data/).

# Aquarius Plant LED

Aquarius Plant LED provides local control of the lamp through native Home
Assistant entities. The 0.3.1 UX update adds a main software-power Light, a clear
mode status, **Resume schedule**, configurable spectral labels and native Tile
sliders. Six independent intensity controls remain available; there is no RGB
wheel or invented master-brightness control. See [Task 004](../../tasks/004-aquarius-ux.md)
for the current release, installation and actual hardware acceptance status.

Version 0.3.1 publishes saved power-origin attributes only after memory has
settled, so the Light immediately describes the correct next On action. The
immutable 0.3.0 candidate retains a known stale-attribute issue after Off; use
0.3.1 for this UX. This repair does not alter protocol commands or add background
restoration.

## Everyday use

- **Following schedule** means the lamp runs its existing stored time-point
  program. **Resume schedule** returns to that program without editing it.
- **Manual override** means the six selected percentages are held. Adjusting an
  intensity slider enters Manual and preserves the other five freshly read
  channel values. The mode selector remains available under configuration for
  existing automations; the dashboard uses the clearer status and button.
- **Lamp Off** requests software Shutdown. It does not switch mains power.
  Before sending Off, HA saves the observed mode and last nonzero Manual mix.
  **On** restores that mix when Off originated from Manual, or resumes the
  existing schedule when Off originated from Following schedule.
- If saved origin is absent, unconfirmed, incompatible, or no longer matches the
  observed Off state, explicit **On resumes the stored schedule**. It never
  invents full-brightness values. A Manual all-zero state can restore its last
  saved nonzero Manual mix; if none exists, the same schedule fallback applies.

Software power is enabled only for controller profiles that passed separate
bounded Shutdown/readback validation. Unknown modes are not interpreted as Off.
An unreachable lamp is unavailable, even if another device has cut mains power.
This integration never operates a Shelly or another mains switch.

## Installation and update

In HAHAPent Manager 0.1.2 or later, use **Refresh** to discover the published
module and **Update** for the existing installation. Follow the Core restart
indication after integration code changes. Back up HA and review startup effects
before restarting. Existing configuration, A–F entity identities and user-assigned
names survive the update; no second integration entry is needed.

For a new installation, select **Install**, then **Configure in HA**. Enter the
already provisioned lamp target and TCP port (default `8080`). The connection
originates from HA. Setup sends only system/channel reads; no provisioning,
network discovery or manufacturer cloud account is required. At runtime the
integration needs neither Manager nor the developer computer.

Use the native integration's **Reconfigure** action if the same lamp's address
changes. Identity belongs to the HA config entry because a verified immutable
serial number is unavailable. Replacing a lamp at the same address with an
identical raw profile cannot be reliably detected.

## Colour labels and intensity sliders

Open the integration's **Configure** options to set the six per-lamp labels.
Defaults remain **Channel A–F** until they are identified. Choose daylight white,
warm white, blue, ruby red, red or green, or enter a distinct short custom label.
The options are versioned and do not impose one lamp's mapping on other variants.
The entity's `protocol_channel` attribute always retains its A–F letter.

Label changes preserve `channel_a` through `channel_f` unique IDs and existing
entity IDs. A name explicitly assigned in Home Assistant's entity registry takes
precedence; clear that custom name if you want the integration's selected label.
Each slider uses integer `0–100%` steps. These values are controller settings,
not calibrated spectral output or wavelength measurements. Ambiguous optical
colours must stay configurable; they must not be guessed from channel order.

## Native dashboard

Use [the complete Tile dashboard example](../../docs/examples/aquarius-tile-dashboard.yaml)
and replace its generic entity IDs with the existing entities. It uses native
`numeric-input` slider features, a software-power toggle, mode status and a
Resume schedule button. Ordinary card taps do nothing. Icon tap or hold opens
More-info deliberately. Dragging a slider should leave the dashboard in place.
Actual desktop/mobile interaction results are recorded separately in Task 004;
a valid YAML example or an emulated viewport alone does not prove iPhone use.

The example's history graph is optional. To stop recording the six channels,
you may add their existing IDs to your own Recorder exclusions, merging with
any current Recorder settings:

```yaml
recorder:
  exclude:
    entities:
      - number.aquarius_example_channel_a
      - number.aquarius_example_channel_b
      - number.aquarius_example_channel_c
      - number.aquarius_example_channel_d
      - number.aquarius_example_channel_e
      - number.aquarius_example_channel_f
```

This is optional configuration guidance. The integration and example do not
change global Recorder settings or retention. Excluded entities will not have
new Recorder history; remove the history graph if it is unwanted.

## Communication, memory and recovery

Setup, startup, polling, reload and reconnect only read the lamp. They never
restore a saved mix or send power, brightness, mode, schedule or clock changes.
Versioned private HA storage retains power intent and Manual memory across a
restart. Saving or loading this memory is not a lamp command. Unsupported future
storage formats remain preserved; Off is blocked when safe persistence cannot
be verified. On retains the documented conservative schedule fallback.

Polling begins every 30 seconds and backs off to five minutes after errors.
Slider changes are debounced and explicit actions are serialized. A fresh mode
and profile guard rejects competing changes to Manual output. Normal schedule
progression in the same Automatic mode is allowed for an explicit action, which
preserves the other five fresh values. An echo or acknowledgement alone never
confirms a command: the write socket remains open through a queried mode/profile
barrier, then a fresh connection confirms output.

Each admitted action has a three-second deadline including debounce and lock
waits. Expiry settles the client transaction and invalidates queued actions;
there is no write retry loop. This cannot bound HTTP admission, recall transmitted
bytes or guarantee recovery through a physical outage. A filesystem save already
in progress must settle before a newer intent can replace it. If a change is
unconfirmed, wait for a successful read, inspect the state and competing apps,
then make a new deliberate action. Runtime recovery never blindly replays output.

Use HAHAPent's owned-code rollback to restore an immutable prior release. Code
rollback does not restore lamp output, schedules or HA configuration. Delete the
native configuration entry through HA before uninstalling owned code; never edit
HA storage manually. Follow [the test-dev recovery runbook](../../docs/test-dev-runbook.md).

## Advanced functions and evidence

The app-visible schedule editor, LPS/SPS/Custom presets, Cloud/Storm effects and
clock sync are future work. Schedule upload, preset replacement, effects/clock
writes, provisioning, factory reset and firmware updates are not exposed.
Automatic schedule stepping/interpolation must be established from actual
observation; the integration does not claim a decoded schedule viewer.

[Task 003](../../tasks/003-led-integration.md) retains the successful six-channel
and Manual/Automatic tests, earlier incidents and corrected recovery reviews.
Immutable 0.1.0/0.1.1 read-only releases and working 0.2.0 remain available.
Task 004 separates synthetic protocol tests, real HA framework tests with fake
transport, private optical observations, actual lamp readback and installation
lifecycle results. A later success does not erase a historical failed experiment.

The protocol implementation was independently derived from supplied AMled 1.6.1
static evidence. No vendor Java, bytecode, original app package, private target,
camera URL or capture is distributed. License selection remains pending.

Platform references: [Light entities](https://developers.home-assistant.io/docs/core/entity/light/),
[Number entities](https://developers.home-assistant.io/docs/core/entity/number/),
[Tile cards](https://www.home-assistant.io/dashboards/tile/),
and [Recorder exclusions](https://www.home-assistant.io/integrations/recorder/).

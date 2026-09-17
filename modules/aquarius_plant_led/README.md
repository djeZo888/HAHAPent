# Aquarius Plant LED

Aquarius Plant LED provides local control of the lamp through native Home
Assistant entities. The 0.4.0 UX includes a main software-power Light, a clear
mode status, **Resume schedule**, configurable spectral labels and native Tile
sliders. An optional compact view adds the native colour-picker dialog and a
0–100% Intensity slider. The detailed view retains all six channel controls.
See [Task 005](../../tasks/005-aquarius-compact-controls.md) for the current release
and actual acceptance; [Task 004](../../tasks/004-aquarius-ux.md) preserves earlier
control and compact-label evidence.

Version 0.3.2 shortens channel names to their configured label, without the
"intensity" suffix. The dashboard example displays entity-only names in
full-width rows, keeping longer labels readable without repeating the lamp name.
This preserves A–F identities, existing entity IDs and owner-assigned names.

The 0.3.1 repair publishes saved power-origin attributes only after memory has
settled, so the Light immediately describes the correct next On action. The
immutable 0.3.0 candidate retains a known stale-attribute issue after Off; use
0.3.1 or later for this UX. This repair does not alter protocol commands or add background
restoration.

## Everyday use

- **Following schedule** means the lamp runs its existing stored time-point
  program. **Resume schedule** returns to that program without editing it.
- **Manual override** means the six selected percentages are held. Adjusting an
  detailed channel slider enters Manual and preserves the other five freshly read
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

## Optional compact colour and intensity

Open the integration's **Configure → Compact controls** options. Enable the
compact controls and explicitly assign A–F to red, green, blue, white or unused.
At least one red, green and blue channel is required. These roles describe the
physical channels; editable colour labels do not determine the mapping. Multiple
red-family channels can share red without guessing which is ruby. Only configure
roles established for your lamp. Leave compact controls disabled when uncertain.

The **Compact** dashboard view has two controls:

- **Colour** opens Home Assistant's native colour-picker dialog.
- **Intensity** scales the current mix from 0 to 100%. Zero requests software
  Off; 100% puts the strongest channel of that mix at its maximum. This is a
  controller percentage, not measured light output or an aquarium PAR setting.

Choosing a colour replaces the channel recipe and selects Manual. White channels
receive the RGB colour's shared white component; mapped primaries receive the
remaining colour. Duplicate roles receive equal percentages. The preview is an
approximation: the lamp has independent spectra, not a calibrated RGB display.
No colour temperature, wavelength or exact visual match is promised.

Changing only Intensity scales all six freshly read channels together, including
an arbitrary mix made in the detailed view, with integer-percentage rounding.
At very low output, this resolution can alter ratios. Colour-only changes keep
current nonzero intensity or a trusted saved Manual intensity. If neither exists,
an explicit colour starts at 5%. Raising intensity without a known nonzero mix
requires choosing a colour first. A non-normalized RGB service value also carries
its own intensity; black requests Off.

The existing Light's plain On/Off behavior is preserved. On restores a confirmed
Manual-origin mix or resumes the existing schedule; selecting a new colour from
Off is a deliberate new Manual recipe. The scheduled lamp can have zero output
while remaining On; explicitly setting the Intensity slider to zero turns it Off.
All state comes from confirmed lamp reads. Setup, options reload, polling and
reconnect never restore or replay a colour. Both views control the same existing
Light and lamp; there is no second integration or device.

The Intensity Number appears only when a valid mapping is enabled. Disabling
compact controls restores On/Off-only Light capabilities; HA may retain an
unavailable Intensity registry entry so its ID and owner name survive re-enabling.

## Colour labels and intensity sliders

Open the integration's **Configure → Channel labels** options to set the six per-lamp labels.
Defaults remain **Channel A–F** until they are identified. Choose daylight white,
warm white, blue, ruby red, red or green, or enter a distinct short custom label.
The options are versioned and do not impose one lamp's mapping on other variants.
The entity's `protocol_channel` attribute always retains its A–F letter.

Label changes preserve `channel_a` through `channel_f` unique IDs and existing
entity IDs. A name explicitly assigned in Home Assistant's entity registry takes
precedence; clear that custom name if you want the integration's selected label.
The Number name is the selected label alone, such as **Daylight white** or the
generic **Channel A**. No global entity-registry rename is needed.
Each slider uses integer `0–100%` steps. These values are controller settings,
not calibrated spectral output or wavelength measurements. Ambiguous optical
colours must stay configurable; they must not be guessed from channel order.

## Native dashboard

Use [the complete Tile dashboard example](../../docs/examples/aquarius-tile-dashboard.yaml)
and replace its generic entity IDs with the existing entities. It uses native
`numeric-input` slider features, a software-power toggle, mode status and a
Resume schedule button. Detailed-view card taps do nothing; the Compact view's
Colour card opens the picker. Icon tap or hold opens More-info deliberately.
Dragging a slider should leave the dashboard in place.
Each channel has a full row and `name: {type: entity}`. This native
[entity-name setting](https://www.home-assistant.io/dashboards/naming/#entity-name)
omits the device prefix while following label-option changes and explicit entity
names; it avoids hard-coded colour labels in the dashboard.
Actual desktop/mobile interaction results are recorded separately in Tasks 004 and 005;
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

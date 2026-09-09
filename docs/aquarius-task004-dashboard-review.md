# Task 004 native dashboard migration review

Status: **PASS — source and synthetic payload review**. This review does not
claim a live dashboard save, browser rendering, or iPhone interaction test.
Reviewed against local Home Assistant 2026.9.1 and its pinned frontend
20260826.6. The module and entity registry are unchanged by this procedure.

## Native API and scope

Use the existing authenticated `/api/websocket` connection. Substitute the
already-owned dashboard URL path for the generic `aquarius-example` below;
the view path is a separate value inside its configuration.

```json
{"id":1,"type":"lovelace/dashboards/list"}
{"id":2,"type":"lovelace/config","url_path":"aquarius-example","force":true}
```

Require one matching dashboard with `mode: "storage"`, and exactly one owned
view with the expected `path`. An unknown dashboard is a stop condition;
do not create a replacement or fall back to the default dashboard.

Saving requires an administrator and a **complete dashboard configuration**:

```python
payload = {
    "id": 3,
    "type": "lovelace/config/save",
    "url_path": owned_dashboard_url_path,
    "config": candidate_dashboard,
}
```

HA provides no view-patch or compare-and-swap revision for this operation. Its
schema accepts a string or dictionary without validating card features; use
a dictionary. Always include `url_path`: omitting it selects a default
dashboard. Do not use dashboard create/update/delete or config/delete.
These contracts were inspected in the installed HA Lovelace `websocket.py`,
`dashboard.py`, and collection WebSocket implementation.

## Constructing the candidate

1. Retain a private original dashboard snapshot and dashboard metadata. Read
   the existing entity registry and select entries for the already-verified
   Aquarius config entry and device, with platform `aquarius_plant_led`.
   Match exact unique IDs `{entry_id}_channel_a` through `_channel_f`,
   `{entry_id}_power`, `{entry_id}_mode_status`, and `{entry_id}_resume_schedule`.
   Require nine distinct, enabled entities in their corresponding domains.
   Use their current `entity_id` values, including owner customizations.
   Never derive IDs from colour labels or displayed names, or write registry
   updates as part of the dashboard migration.
2. Load [the generic example](examples/aquarius-tile-dashboard.yaml). Replace
   only exact placeholder entity values with that verified mapping, including
   the optional history card. Leave Tile `name` unset so HA uses entity names.
   Confirm the Number states expose min 0, max 100, step 1 and unit `%`.
3. Deep-copy the original dashboard. In its unique owned view, replace only
   `cards` with the example view's `cards`. Keep the original view path, title,
   icon, visibility, badges and other metadata. Keep every other view and
   top-level property exactly equal to the snapshot. The example's dashboard
   title and `aquarium` view path are **not** migration replacements.
4. Require a compatible ordinary card view: no dashboard/view strategy,
   Sections layout, panel layout, or other unreviewed layout mode. If the
   existing view differs, prepare an explicit view-local adaptation first.
   This procedure does not replace unrelated cards in an unowned view.
5. Confirm nine native Tiles: six Number sliders, one Light toggle, one
   read-only mode Sensor, and one Resume schedule Button. Every Tile disables
   ordinary body taps and reserves icon taps/holds for More info. History is
   optional and uses existing data; no Recorder or retention change is needed.

Immediately before saving, re-read configuration and metadata and compare
with the original snapshot. If either changed, rebuild and review the
candidate. This narrows a concurrent-edit race; HA offers no atomic revision
guard. Save once, then read back the complete config and require equality with
the candidate, unchanged other views, and unchanged dashboard metadata.

Storage-mode `force: true` does not bypass HA's in-memory config cache. HA's
Store also logs some write failures without raising them to this handler.
Therefore API success and readback establish the served configuration, not
independent disk durability. The coordinator can additionally verify the
existing owned `.storage/lovelace.{dashboard_metadata_id}` record privately
through authorized HA-side read access; never edit storage files directly or
restart Core solely for this check. On an uncertain result, inspect current
state first. A rollback must also preserve concurrent edits: only restore the
private original snapshot when the current config still exactly matches this
migration's candidate.

## Tile behavior established from source

The pinned feature type supports `type: numeric-input` and `style: slider`.
For Number entities it takes bounds, step and unit from entity attributes;
its value-change handler calls `number.set_value` with the displayed entity ID.
[Feature implementation](https://github.com/home-assistant/frontend/blob/20260826.6/src/panels/lovelace/card-features/hui-numeric-input-card-feature.ts),
[feature types](https://github.com/home-assistant/frontend/blob/20260826.6/src/panels/lovelace/card-features/types.ts).

Tile background/icon actions are separate from features, and the feature
container stops click/action propagation. Thus `tap_action: none` suppresses
ordinary card-body behavior while retaining the slider and dedicated feature
buttons. More info remains explicitly available on the icon and hold actions.
[Tile card](https://github.com/home-assistant/frontend/blob/20260826.6/src/panels/lovelace/cards/hui-tile-card.ts),
[Tile container](https://github.com/home-assistant/frontend/blob/20260826.6/src/components/tile/ha-tile-container.ts).

The slider commits on a completed drag or a tap on the slider itself; a tap
on the slider can therefore change output. Drag movement updates its local
value, and a cancelled pan restores that local value without committing.
Horizontal controls permit vertical touch scrolling. This is source behavior,
not an observed iPhone gesture result.
[Slider implementation](https://github.com/home-assistant/frontend/blob/20260826.6/src/components/ha-control-slider.ts).

The dedicated Button feature calls `button.press` for a Button entity. Its
Resume schedule label is presentation only; it targets the mapped native
entity rather than a script or a custom dashboard service.
[Button feature](https://github.com/home-assistant/frontend/blob/20260826.6/src/panels/lovelace/card-features/hui-button-card-feature.ts).

## Executed checks and remaining UI evidence

- **PASS, synthetic:** parsed example YAML; nine Tiles and six explicit slider
  features; action settings; no hard-coded Tile names; copied three-view
  fixture preserves both unrelated views and all non-card metadata.
- **PASS, native schema:** imported the installed HA WebSocket handlers and
  validated the explicit read and complete save messages with their actual
  Voluptuous schemas. No HA instance or lamp was contacted.
- Native integration/service tests are separate evidence. They exercise HA
  entities and service behavior, not the frontend's rendered components.
- **NOT_TESTED here:** live dashboard persistence, browser layout, and actual
  iPhone Safari/Companion touch handling. Configuration readback cannot replace
  these checks. A future isolated frontend component test can use fake states
  and a captured `hass.callService` to verify one slider commit without a
  `hass-more-info` event; that would still be synthetic UI evidence.

The coordinator records any later live migration and UI acceptance in the
current task report. This review remains a description of the offline gate.

"""Real HA colour/number services and options with synthetic controller state."""

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_socket
from custom_components.aquarius_plant_led import protocol
from custom_components.aquarius_plant_led.compact import (
    CONF_CHANNEL_ROLES,
    CONF_CHANNEL_ROLES_VERSION,
)
from custom_components.aquarius_plant_led.const import (
    CHANNEL_KEYS,
    CONF_CHANNEL_LABELS,
    CONF_CHANNEL_LABELS_VERSION,
    DOMAIN,
    NAME,
    default_channel_labels,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.aquarius_tcp_helpers import SYNTHETIC_PROFILES, SyntheticLamp


def fictional_roles():
    """An arbitrary synthetic mapping, never a claim about an owner's lamp."""
    return dict(zip(CHANNEL_KEYS, ("red", "green", "blue", "white", "red", "unused")))


def role_options():
    return {CONF_CHANNEL_ROLES_VERSION: 1, CONF_CHANNEL_ROLES: fictional_roles()}


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


async def start_compact_options(hass, entry):
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU
    assert menu["menu_options"] == ["labels", "compact"]
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "compact"}
    )


@pytest.fixture
async def compact_entry(hass, config_entry, mock_client):
    hass.config_entries.async_update_entry(config_entry, options=role_options())
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
async def compact_loopback_entry(hass, socket_enabled):
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    lamp = SyntheticLamp()
    lamp.channel_operation = 0xFA
    port = await lamp.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={"host": "127.0.0.1", "port": port},
        options=role_options(),
    )
    entry.add_to_hass(hass)
    with (
        patch.object(protocol, "VERIFIED_WRITE_PROFILES", SYNTHETIC_PROFILES),
        patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", SYNTHETIC_PROFILES),
    ):
        try:
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            yield lamp, entry
        finally:
            if entry.state is ConfigEntryState.LOADED:
                await hass.config_entries.async_unload(entry.entry_id)
            await lamp.close()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"brightness": 1}, {"rgb_color": None, "intensity": 1}),
        ({"brightness": 127}, {"rgb_color": None, "intensity": 50}),
        ({"brightness": 128}, {"rgb_color": None, "intensity": 50}),
        ({"brightness": 255}, {"rgb_color": None, "intensity": 100}),
        ({"brightness_pct": 1}, {"rgb_color": None, "intensity": 1}),
        ({"brightness_pct": 33}, {"rgb_color": None, "intensity": 33}),
        ({"rgb_color": [128, 0, 0]}, {"rgb_color": (128, 0, 0), "intensity": None}),
        (
            {"rgb_color": [128, 0, 0], "brightness": 255},
            {"rgb_color": (128, 0, 0), "intensity": 100},
        ),
        (
            {"hs_color": [120, 100], "brightness_pct": 20},
            {"rgb_color": (0, 255, 0), "intensity": 20},
        ),
    ],
)
async def test_native_light_payload_conversion_applies_rgb_amplitude_only_in_mixer(
    hass, compact_entry, payload, expected
):
    coordinator = compact_entry.runtime_data
    with (
        patch.object(coordinator, "async_set_compact", new_callable=AsyncMock) as compact,
        patch.object(coordinator, "async_turn_on", new_callable=AsyncMock) as plain_on,
        patch.object(coordinator, "async_turn_off", new_callable=AsyncMock) as off,
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id(hass, compact_entry, "light", "power"), **payload},
            blocking=True,
        )
        compact.assert_awaited_once_with(**expected)
        plain_on.assert_not_awaited()
        off.assert_not_awaited()


@pytest.mark.parametrize("payload", ({"brightness_pct": 0}, {"rgb_color": [0, 0, 0]}))
async def test_native_zero_and_black_use_existing_off_path(hass, compact_entry, payload):
    coordinator = compact_entry.runtime_data
    with (
        patch.object(coordinator, "async_set_compact", new_callable=AsyncMock) as compact,
        patch.object(coordinator, "async_turn_off", new_callable=AsyncMock) as off,
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id(hass, compact_entry, "light", "power"), **payload},
            blocking=True,
        )
        off.assert_awaited_once_with()
        compact.assert_not_awaited()


async def test_bare_on_keeps_saved_origin_api(hass, compact_entry):
    coordinator = compact_entry.runtime_data
    with (
        patch.object(coordinator, "async_set_compact", new_callable=AsyncMock) as compact,
        patch.object(coordinator, "async_turn_on", new_callable=AsyncMock) as plain_on,
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id(hass, compact_entry, "light", "power")},
            blocking=True,
        )
        plain_on.assert_awaited_once_with()
        compact.assert_not_awaited()


@pytest.mark.parametrize("value", (0, 1, 37, 100))
async def test_native_intensity_number_accepts_literal_zero_to_100(hass, compact_entry, value):
    intensity_id = entity_id(hass, compact_entry, "number", "intensity")
    state = hass.states.get(intensity_id)
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == 100
    assert state.attributes["step"] == 1
    assert state.attributes["unit_of_measurement"] == "%"
    assert er.async_get(hass).async_get(intensity_id).original_name == "Intensity"
    with patch.object(
        compact_entry.runtime_data, "async_set_compact", new_callable=AsyncMock
    ) as compact:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": intensity_id, "value": value}, blocking=True
        )
        compact.assert_awaited_once_with(intensity=value)


async def test_rest_state_reports_actual_peak_and_approximation_for_detailed_and_auto_mix(
    hass, hass_client, compact_entry, observed_state
):
    assert await async_setup_component(hass, "api", {})
    client = await hass_client()
    light_id = entity_id(hass, compact_entry, "light", "power")
    for mode in (1, 0):
        compact_entry.runtime_data.async_set_updated_data(
            replace(observed_state, system=replace(observed_state.system, mode_raw=mode))
        )
        response = await client.get(f"/api/states/{light_id}")
        assert response.status == 200
        state = await response.json()
        assert state["state"] == "on"
        attributes = state["attributes"]
        assert attributes["supported_color_modes"] == ["rgb"]
        assert attributes["color_mode"] == "rgb"
        assert attributes["brightness"] == 153  # Actual maximum is channel F's 60%.
        assert attributes["rgb_color"] == [255, 170, 198]
        assert attributes["colour_representation"].startswith("Approximate")
        assert "not measured luminosity" in attributes["intensity_basis"]
    assert hass.states.get(entity_id(hass, compact_entry, "number", "intensity")).state == "60"


async def test_off_colour_basis_requires_confirmed_manual_origin_and_reports_zero_intensity(
    hass, compact_entry, observed_state
):
    coordinator = compact_entry.runtime_data
    off = replace(
        observed_state, channels=(0,) * 6, system=replace(observed_state.system, mode_raw=8)
    )
    await coordinator.power_memory.async_prepare_off(observed_state)
    await coordinator.power_memory.async_confirm_off(off)
    coordinator.async_set_updated_data(off)
    light_id = entity_id(hass, compact_entry, "light", "power")
    light = hass.data["light"].get_entity(light_id)
    assert light.rgb_color == (255, 170, 198)
    assert light.brightness == 0
    assert hass.states.get(light_id).state == "off"
    assert hass.states.get(entity_id(hass, compact_entry, "number", "intensity")).state == "0"
    # A changed Off observation must not show a remembered colour as current truth.
    coordinator.async_set_updated_data(replace(off, channels=(1, 0, 0, 0, 0, 0)))
    assert light.rgb_color is None


async def test_compact_options_form_is_serializable_and_disabled_until_explicit_mapping(
    hass, config_entry, mock_client
):
    form = await start_compact_options(hass, config_entry)
    serialized = FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(form)
    json.dumps(serialized)
    fields = {field["name"]: field for field in serialized["data_schema"]}
    assert fields["enabled"]["default"] is False
    for key in CHANNEL_KEYS:
        assert fields[key]["default"] == "unused"
        assert fields[key]["selector"]["select"]["options"] == [
            "unused",
            "red",
            "green",
            "blue",
            "white",
        ]
    mock_client.refresh.assert_not_awaited()
    assert config_entry.options == {}


async def test_role_enable_disable_reload_preserves_existing_ids_names_and_off_memory(
    hass, loaded_entry, mock_client, observed_state, hass_storage
):
    registry = er.async_get(hass)
    light_id = entity_id(hass, loaded_entry, "light", "power")
    registry.async_update_entity(light_id, name="Owner's lamp")
    before_ids = {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    memory = loaded_entry.runtime_data.power_memory
    off = replace(
        observed_state, channels=(0,) * 6, system=replace(observed_state.system, mode_raw=8)
    )
    await memory.async_prepare_off(observed_state)
    await memory.async_confirm_off(off)
    saved = deepcopy(hass_storage[memory.key])
    mock_client.refresh.side_effect = None
    mock_client.refresh.return_value = off
    mock_client.reset_mock()
    intensity_identity = None
    for enabled in (True, False, True):
        form = await start_compact_options(hass, loaded_entry)
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {"enabled": enabled, **fictional_roles()}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        after_ids = {
            entry.unique_id: entry.entity_id
            for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
        }
        assert all(after_ids[key] == value for key, value in before_ids.items())
        assert hass.states.get(light_id).name == "Owner's lamp"
        assert hass.states.get(light_id).attributes["supported_color_modes"] == (
            ["rgb"] if enabled else ["onoff"]
        )
        intensity_id = entity_id(hass, loaded_entry, "number", "intensity")
        if intensity_identity is None:
            registry.async_update_entity(intensity_id, name="Owner's intensity")
            intensity_identity = intensity_id
        assert intensity_id == intensity_identity
        assert registry.async_get(intensity_id).name == "Owner's intensity"
        # HA retains a registry placeholder when an optional platform entity is
        # absent, preserving its identity for a later explicit re-enable.
        assert hass.states.get(intensity_id).state == ("0" if enabled else "unavailable")
        assert (hass.data["number"].get_entity(intensity_id) is not None) is enabled
        assert hass_storage[memory.key] == saved
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()
    mock_client.turn_on.assert_not_awaited()
    mock_client.turn_off.assert_not_awaited()


async def test_labels_do_not_change_explicit_roles_and_role_options_preserve_labels(
    hass, compact_entry, mock_client
):
    original_roles = dict(compact_entry.options)
    original_roles["owner_option"] = "keep"
    hass.config_entries.async_update_entry(compact_entry, options=original_roles)
    menu = await hass.config_entries.options.async_init(compact_entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "labels"}
    )
    labels = default_channel_labels()
    labels["channel_a"] = "Owner display only"
    result = await hass.config_entries.options.async_configure(form["flow_id"], labels)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert compact_entry.options[CONF_CHANNEL_ROLES] == fictional_roles()
    assert compact_entry.options[CONF_CHANNEL_LABELS] == labels
    form = await start_compact_options(hass, compact_entry)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"enabled": False, **fictional_roles()}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert compact_entry.options == {
        "owner_option": "keep",
        CONF_CHANNEL_LABELS_VERSION: 1,
        CONF_CHANNEL_LABELS: labels,
    }
    mock_client.turn_on.assert_not_awaited()
    mock_client.turn_off.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize("version", (2, True, "1"))
async def test_future_role_schema_is_preserved_and_disables_compact_capabilities(
    hass, config_entry, mock_client, version
):
    options = {**role_options(), CONF_CHANNEL_ROLES_VERSION: version, "owner_option": "keep"}
    hass.config_entries.async_update_entry(config_entry, options=options)
    result = await start_compact_options(hass, config_entry)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_role_version"
    assert config_entry.options == options
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    light = hass.states.get(entity_id(hass, config_entry, "light", "power"))
    assert light.attributes["supported_color_modes"] == ["onoff"]
    assert entity_id(hass, config_entry, "number", "intensity") is None


async def test_invalid_roles_do_not_save_or_read_controller(hass, config_entry, mock_client):
    form = await start_compact_options(hass, config_entry)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"enabled": True, **{key: "white" for key in CHANNEL_KEYS}}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_roles"}
    json.dumps(FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(result))
    assert config_entry.options == {}
    mock_client.refresh.assert_not_awaited()


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_http_colour_and_intensity_use_one_real_client_vector_transaction(
    hass, hass_client, compact_loopback_entry
):
    """Native HTTP dispatch plus actual protocol, using a loopback simulator only."""
    lamp, entry = compact_loopback_entry
    assert await async_setup_component(hass, "api", {})
    client = await hass_client()
    light_id = entity_id(hass, entry, "light", "power")
    response = await client.post(
        "/api/services/light/turn_on",
        json={"entity_id": light_id, "rgb_color": [128, 0, 0], "brightness_pct": 100},
    )
    assert response.status == 200
    # Input RGB has its own half-intensity. It is applied once, not normalized
    # away or multiplied twice. Duplicated red roles receive equal 50% levels.
    expected = (50, 0, 0, 0, 50, 0)
    assert lamp.channels == expected
    assert lamp.mode == 1
    assert lamp.writes == [protocol.channel_write_frame(expected), protocol.mode_frame(1)]
    response = await client.get(f"/api/states/{light_id}")
    state = await response.json()
    assert state["attributes"]["rgb_color"] == [255, 0, 0]
    assert state["attributes"]["brightness"] == 128
    assert hass.states.get(entity_id(hass, entry, "number", "intensity")).state == "50"


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_real_intensity_scales_all_channels_then_zero_off_and_bare_on_restore(
    hass, compact_loopback_entry
):
    lamp, entry = compact_loopback_entry
    lamp.mode = 1
    lamp.channels = (10, 20, 30, 40, 50, 60)
    await entry.runtime_data.async_refresh()
    intensity_id = entity_id(hass, entry, "number", "intensity")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": intensity_id, "value": 30}, blocking=True
    )
    expected = (5, 10, 15, 20, 25, 30)
    assert lamp.channels == expected  # Includes the channel labelled unused by the picker.

    def clear_shutdown(frame, response):
        if frame == protocol.mode_frame(8):
            lamp.channels = (0,) * 6
        return response

    lamp.response_override = clear_shutdown
    await hass.services.async_call(
        "number", "set_value", {"entity_id": intensity_id, "value": 0}, blocking=True
    )
    assert lamp.mode == 8
    assert lamp.channels == (0,) * 6
    assert entry.runtime_data.power_memory.manual_restore(entry.runtime_data.data)[0] == expected
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id(hass, entry, "light", "power")}, blocking=True
    )
    assert lamp.mode == 1
    assert lamp.channels == expected
    assert lamp.writes == [
        protocol.channel_write_frame(expected),
        protocol.mode_frame(1),
        protocol.mode_frame(8),
        protocol.mode_frame(1),
        protocol.channel_write_frame(expected),
        protocol.mode_frame(1),
    ]


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_colour_only_from_zero_automatic_uses_five_percent_and_readback(
    hass, compact_loopback_entry
):
    lamp, entry = compact_loopback_entry
    lamp.mode = 0
    lamp.channels = (0,) * 6
    await entry.runtime_data.async_refresh()
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": entity_id(hass, entry, "light", "power"), "rgb_color": [0, 255, 0]},
        blocking=True,
    )
    assert lamp.mode == 1
    assert lamp.channels == (0, 5, 0, 0, 0, 0)
    assert hass.states.get(entity_id(hass, entry, "number", "intensity")).state == "5"


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_native_intensity_without_a_basis_explains_choose_colour_and_sends_no_write(
    hass, compact_loopback_entry
):
    lamp, entry = compact_loopback_entry
    lamp.mode = 0
    lamp.channels = (0,) * 6
    await entry.runtime_data.async_refresh()
    with pytest.raises(ServiceValidationError, match="Choose a colour first"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, entry, "number", "intensity"), "value": 5},
            blocking=True,
        )
    assert lamp.writes == []
    assert lamp.channels == (0,) * 6
    assert lamp.mode == 0
    assert entry.runtime_data.last_update_success
    assert hass.states.get(entity_id(hass, entry, "number", "intensity")).state == "0"
    # The rejected input was a known no-write condition, so its explanation
    # must be actionable immediately without waiting for a recovery poll.
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            "entity_id": entity_id(hass, entry, "light", "power"),
            "rgb_color": [0, 255, 0],
            "brightness_pct": 5,
        },
        blocking=True,
    )
    expected = (0, 5, 0, 0, 0, 0)
    assert lamp.channels == expected
    assert lamp.writes == [protocol.channel_write_frame(expected), protocol.mode_frame(1)]

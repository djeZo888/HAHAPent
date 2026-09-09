"""Native options persistence, serialization and stable identity; fictional labels only."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from custom_components.aquarius_plant_led.const import (
    CHANNEL_KEYS,
    CHANNEL_LABEL_CHOICES,
    CHANNEL_LABELS_VERSION,
    CONF_CHANNEL_LABELS,
    CONF_CHANNEL_LABELS_VERSION,
    channel_labels_from_options,
    default_channel_labels,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView


def fictional_labels():
    """These arbitrary names do not describe any observed lamp mapping."""
    return dict(
        zip(CHANNEL_KEYS, ("Blue", "Red", "Green", "Warm white", "Ruby red", "Daylight white"))
    )


async def test_options_form_uses_serializable_selectors_and_unknown_mapping_defaults(
    hass, config_entry, mock_client
):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    serialized = FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(result)
    json.dumps(serialized)
    fields = {field["name"]: field for field in serialized["data_schema"]}
    assert set(fields) == set(CHANNEL_KEYS)
    for key, label in default_channel_labels().items():
        assert fields[key]["default"] == label
        selector = fields[key]["selector"]["select"]
        assert selector["custom_value"] is True
        assert selector["mode"] == "dropdown"
        assert selector["options"] == [label, *CHANNEL_LABEL_CHOICES]
    assert config_entry.options == {}
    mock_client.refresh.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_options_save_normalizes_plain_labels_and_preserves_unrelated_options(
    hass, config_entry, mock_client
):
    hass.config_entries.async_update_entry(config_entry, options={"unrelated_option": "preserve"})
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    labels = fictional_labels()
    labels["channel_a"] = "  Blue   (left)  "
    result = await hass.config_entries.options.async_configure(result["flow_id"], labels)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_CHANNEL_LABELS_VERSION] == CHANNEL_LABELS_VERSION
    assert config_entry.options[CONF_CHANNEL_LABELS]["channel_a"] == "Blue (left)"
    assert config_entry.options["unrelated_option"] == "preserve"
    reopened = await hass.config_entries.options.async_init(config_entry.entry_id)
    serialized = FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(reopened)
    fields = {field["name"]: field for field in serialized["data_schema"]}
    assert fields["channel_a"]["default"] == "Blue (left)"
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_label_reload_preserves_number_ids_device_identity_and_user_custom_name(
    hass, loaded_entry, mock_client
):
    registry = er.async_get(hass)
    before = er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    channel_b = next(entry for entry in before if entry.unique_id.endswith("_channel_b"))
    registry.async_update_entity(
        channel_b.entity_id, new_entity_id="number.owner_named_channel", name="Owner's custom label"
    )
    await hass.async_block_till_done()
    before_ids = {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    device_id = dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)[0].id
    mock_client.reset_mock()
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], fictional_labels()
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert before_ids == {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    assert (
        dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)[0].id
        == device_id
    )
    assert registry.async_get("number.owner_named_channel").name == "Owner's custom label"
    assert "Owner's custom label" in hass.states.get("number.owner_named_channel").name
    for key, label in fictional_labels().items():
        entity_id = before_ids[f"{loaded_entry.entry_id}_{key}"]
        entry = registry.async_get(entity_id)
        assert entry.original_name == f"{label} intensity"
        assert hass.states.get(entity_id).attributes["protocol_channel"] == key[-1].upper()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_default_reset_restores_generic_names_without_replacing_entities(
    hass, loaded_entry, mock_client
):
    registry = er.async_get(hass)
    ids = {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    for labels in (fictional_labels(), default_channel_labels()):
        result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], labels)
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
    for key, label in default_channel_labels().items():
        assert registry.async_get(ids[f"{loaded_entry.entry_id}_{key}"]).original_name == label
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_labels_reload_preserves_confirmed_off_memory_without_restoration(
    hass, loaded_entry, mock_client, observed_state, hass_storage
):
    """A names-only reload must not consume or apply a prior explicit Off intent."""
    coordinator = loaded_entry.runtime_data
    memory = coordinator.power_memory
    off = replace(observed_state, system=replace(observed_state.system, mode_raw=8))
    await memory.async_prepare_off(observed_state)
    await memory.async_confirm_off(off)
    saved = deepcopy(hass_storage[memory.key])
    registry = er.async_get(hass)
    before_ids = {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    mock_client.refresh.side_effect = None
    mock_client.refresh.return_value = off
    mock_client.reset_mock()

    flow = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(flow["flow_id"], fictional_labels())
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    reloaded = loaded_entry.runtime_data
    assert reloaded is not coordinator
    assert reloaded.power_memory.key == memory.key
    assert reloaded.power_memory.manual_restore(off)[0] == observed_state.channels
    assert hass_storage[memory.key] == saved
    assert before_ids == {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    mock_client.refresh.assert_awaited()
    mock_client.turn_on.assert_not_awaited()
    mock_client.turn_off.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize(
    ("label", "error"),
    [
        ("", "invalid_label"),
        ("  ", "invalid_label"),
        ("X" * 41, "invalid_label"),
        ("Blue\nlight", "invalid_label"),
        ("Blue\x00light", "invalid_label"),
        ("Blue\u202elight", "invalid_label"),
        ("<b>Blue</b>", "invalid_label"),
        (" RED ", "duplicate_label"),
    ],
)
async def test_invalid_labels_return_serializable_error_without_changes(
    hass, config_entry, mock_client, label, error
):
    labels = fictional_labels()
    labels["channel_c"] = label
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], labels)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"channel_c": error}
    json.dumps(FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(result))
    assert config_entry.options == {}
    mock_client.refresh.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize("version", (2, True, "1", -1))
async def test_unknown_label_schema_is_not_overwritten(hass, config_entry, mock_client, version):
    options = {CONF_CHANNEL_LABELS_VERSION: version, CONF_CHANNEL_LABELS: fictional_labels()}
    hass.config_entries.async_update_entry(config_entry, options=options)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_label_version"
    assert config_entry.options == options
    assert channel_labels_from_options(config_entry.options) == default_channel_labels()
    mock_client.refresh.assert_not_awaited()


@pytest.mark.parametrize(
    "labels", (None, {}, {"channel_a": "Blue"}, {key: "Duplicate" for key in CHANNEL_KEYS})
)
async def test_malformed_stored_mapping_keeps_generic_protocol_names(hass, config_entry, labels):
    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_CHANNEL_LABELS_VERSION: 1, CONF_CHANNEL_LABELS: labels},
    )
    assert channel_labels_from_options(config_entry.options) == default_channel_labels()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    serialized = FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(result)
    assert {
        field["name"]: field["default"] for field in serialized["data_schema"]
    } == default_channel_labels()

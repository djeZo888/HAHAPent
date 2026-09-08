"""Config flows execute inside Home Assistant, with transport mocked only."""

import asyncio
import json
from unittest.mock import patch

import pytest
from custom_components.aquarius_plant_led.client import AquariusError
from custom_components.aquarius_plant_led.const import DOMAIN
from custom_components.aquarius_plant_led.protocol import ProtocolError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView


@pytest.mark.parametrize("source", (config_entries.SOURCE_USER, config_entries.SOURCE_RECONFIGURE))
async def test_native_form_serializes_for_http_response(hass, config_entry, mock_client, source):
    context = {"source": source}
    if source == config_entries.SOURCE_RECONFIGURE:
        context["entry_id"] = config_entry.entry_id
    result = await hass.config_entries.flow.async_init(DOMAIN, context=context)
    # This is the real HA HTTP view's conversion, which direct flow tests do
    # not execute. An arbitrary callable in a field schema fails here.
    serialized = FlowManagerIndexView(hass.config_entries.flow)._prepare_result_json(result)
    json.dumps(serialized)
    fields = {field["name"]: field for field in serialized["data_schema"]}
    assert fields["host"]["type"] == "string"
    assert fields["port"]["default"] == 8080
    mock_client.refresh.assert_not_awaited()


@pytest.mark.parametrize("source", (config_entries.SOURCE_USER, config_entries.SOURCE_RECONFIGURE))
@pytest.mark.parametrize("host", ("http://lamp.example.invalid:8080", "   "))
async def test_invalid_host_returns_serializable_field_error_without_network(
    hass, config_entry, mock_client, source, host
):
    context = {"source": source}
    if source == config_entries.SOURCE_RECONFIGURE:
        context["entry_id"] = config_entry.entry_id
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context=context, data={"host": host, "port": 8080}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"host": "invalid_host"}
    serialized = FlowManagerIndexView(hass.config_entries.flow)._prepare_result_json(result)
    json.dumps(serialized)
    assert config_entry.data["host"] == "lamp.example.invalid"
    mock_client.refresh.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_user_setup_is_read_only_and_normalizes_endpoint(hass, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    with patch("custom_components.aquarius_plant_led.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": " Lamp.Example.Invalid. ", "port": 8080}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "lamp.example.invalid", "port": 8080}
    assert result["result"].unique_id is None
    mock_client.refresh.assert_awaited_once()
    mock_client.close.assert_awaited_once()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_duplicate_entry_rejected_before_network(hass, config_entry, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={"host": "LAMP.EXAMPLE.INVALID.", "port": 8080},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.refresh.assert_not_awaited()


async def test_inflight_duplicate_is_rejected(hass, mock_client, observed_state):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh():
        started.set()
        await release.wait()
        return observed_state

    mock_client.refresh.side_effect = slow_refresh
    with patch("custom_components.aquarius_plant_led.async_setup_entry", return_value=True):
        first = asyncio.create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data={"host": "lamp.example.invalid", "port": 8080},
            )
        )
        await started.wait()
        second = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={"host": "lamp.example.invalid", "port": 8080},
        )
        assert second["reason"] == "already_in_progress"
        release.set()
        assert (await first)["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    mock_client.refresh.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AquariusError("Synthetic offline"), "cannot_connect"),
        (ProtocolError("Bad"), "invalid_response"),
    ],
)
async def test_connection_errors_keep_form_without_writes(hass, mock_client, error, expected):
    mock_client.refresh.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={"host": "lamp.example.invalid", "port": 8080},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    mock_client.close.assert_awaited_once()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_reconfigure_preserves_entry_device_entity_and_custom_name(
    hass, loaded_entry, mock_client
):
    registry = er.async_get(hass)
    before = er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    ids = {entry.unique_id: entry.entity_id for entry in before}
    renamed = next(entry for entry in before if entry.unique_id.endswith("channel_c"))
    registry.async_update_entity(renamed.entity_id, name="My aquarium blue")
    device = dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)[0]
    mock_client.reset_mock()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": loaded_entry.entry_id},
        data={"host": "replacement-address.example.invalid", "port": 8080},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert loaded_entry.data["host"] == "replacement-address.example.invalid"
    assert ids == {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    }
    assert registry.async_get(renamed.entity_id).name == "My aquarium blue"
    assert (
        dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)[0].id
        == device.id
    )
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_reconfigure_duplicate_endpoint_is_rejected(hass, loaded_entry, mock_client):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    second = MockConfigEntry(domain=DOMAIN, data={"host": "second.example.invalid", "port": 8080})
    second.add_to_hass(hass)
    mock_client.refresh.reset_mock()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": loaded_entry.entry_id},
        data={"host": " SECOND.EXAMPLE.INVALID. ", "port": 8080},
    )
    assert result["reason"] == "already_configured"
    assert loaded_entry.data["host"] == "lamp.example.invalid"
    mock_client.refresh.assert_not_awaited()


async def test_future_entry_migration_is_rejected(hass):
    from custom_components.aquarius_plant_led import async_migrate_entry
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    future = MockConfigEntry(domain=DOMAIN, version=2)
    assert not await async_migrate_entry(hass, future)
    assert future.version == 2

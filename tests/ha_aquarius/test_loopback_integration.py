"""Actual HA and actual TCP client together, against a loopback-only simulator."""

import asyncio
from unittest.mock import patch

import pytest
import pytest_socket
from custom_components.aquarius_plant_led import protocol
from custom_components.aquarius_plant_led.client import AquariusClient
from custom_components.aquarius_plant_led.const import DOMAIN, NAME
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.aquarius_tcp_helpers import SYNTHETIC_PROFILES, SyntheticLamp

# HA's fixture plugin also disables socket creation. The scoped fixture below
# restores socket creation, then immediately restricts connects to loopback.
pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


@pytest.fixture
def loopback_network(socket_enabled):
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)


@pytest.fixture
async def loopback_entry(hass, loopback_network):
    lamp = SyntheticLamp()
    lamp.controller = (0x14, 0x32)
    lamp.channel_operation = 0xFA
    port = await lamp.start()
    entry = MockConfigEntry(domain=DOMAIN, title=NAME, data={"host": "127.0.0.1", "port": port})
    entry.add_to_hass(hass)
    with patch.object(protocol, "VERIFIED_WRITE_PROFILES", SYNTHETIC_PROFILES):
        try:
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            yield lamp, entry
        finally:
            if entry.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(entry.entry_id)
            await lamp.close()


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


async def test_native_service_protocol_readback_and_readonly_reload(hass, loopback_entry):
    lamp, entry = loopback_entry
    coordinator = entry.runtime_data
    assert isinstance(coordinator.client, AquariusClient)
    assert lamp.frames == [protocol.SYSTEM_QUERY, protocol.CHANNEL_QUERY]
    assert lamp.writes == []
    channel = entity_id(hass, entry, "number", "channel_c")
    mode = entity_id(hass, entry, "select", "operating_mode")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": channel, "value": 31}, blocking=True
    )
    assert lamp.channels == (10, 20, 31, 40, 50, 60)
    assert hass.states.get(channel).state == "31"
    assert lamp.mode == protocol.MODE_MANUAL
    assert lamp.writes == [
        protocol.channel_write_frame(lamp.channels, swap_cd=True),
        protocol.mode_frame(protocol.MODE_MANUAL),
    ]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": mode, "option": "automatic_program"},
        blocking=True,
    )
    assert lamp.mode == protocol.MODE_AUTOMATIC
    assert hass.states.get(mode).state == "automatic_program"
    writes = list(lamp.writes)
    connections = lamp.connections

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.client is not coordinator.client
    assert lamp.connections > connections
    assert lamp.writes == writes
    assert hass.states.get(channel).state == "31"
    assert hass.states.get(mode).state == "automatic_program"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert lamp.writes == writes


async def test_ignored_write_echo_is_unavailable_then_recovers_without_replay(hass, loopback_entry):
    lamp, entry = loopback_entry
    coordinator = entry.runtime_data
    channel = entity_id(hass, entry, "number", "channel_c")
    lamp.ignore_writes = True
    lamp.echo_writes = True
    with pytest.raises(HomeAssistantError, match="No command was retried"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": channel, "value": 31}, blocking=True
        )
    assert lamp.channels == (10, 20, 30, 40, 50, 60)
    assert not coordinator.last_update_success
    assert hass.states.get(channel).state == "unavailable"
    assert lamp.writes == [
        protocol.channel_write_frame((10, 20, 31, 40, 50, 60), swap_cd=True),
        protocol.mode_frame(protocol.MODE_MANUAL),
    ]
    # Initial setup, prewrite, then an independent socket for real readback.
    assert lamp.connections == 3
    writes = list(lamp.writes)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert hass.states.get(channel).state == "30"
    assert lamp.writes == writes


@pytest.mark.parametrize("phase", ("client_lock", "pre_read"))
async def test_native_service_deadline_settles_real_client_and_cannot_write_after_release(
    hass, loopback_entry, phase
):
    lamp, entry = loopback_entry
    coordinator = entry.runtime_data
    client = coordinator.client
    if phase == "client_lock":
        await client._lock.acquire()
    else:
        lamp.response_override = lambda frame, response: None
    with (
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0),
        patch("custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.04),
    ):
        with pytest.raises(HomeAssistantError, match="expired before completion"):
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id(hass, entry, "number", "channel_a"), "value": 11},
                blocking=True,
            )
    assert coordinator._active_command is None
    assert client._active_task is None
    assert client._writer is None
    assert not coordinator.last_update_success
    if phase == "client_lock":
        client._lock.release()
    lamp.response_override = None
    await asyncio.sleep(0.06)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert lamp.writes == []


async def test_native_timeout_after_channel_write_never_sends_delayed_mode_or_restore(
    hass, loopback_entry
):
    lamp, entry = loopback_entry
    coordinator = entry.runtime_data
    with (
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0),
        patch("custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.1),
        patch("custom_components.aquarius_plant_led.client.SYSTEM_CHANNEL_DELAY", 0.001),
        patch("custom_components.aquarius_plant_led.client.MANUAL_SAVE_DELAY", 0.3),
    ):
        with pytest.raises(HomeAssistantError, match="expired before completion"):
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id(hass, entry, "number", "channel_a"), "value": 11},
                blocking=True,
            )
        assert coordinator.client._active_task is None
        assert coordinator.client._writer is None
        assert not coordinator.last_update_success
        assert len(lamp.writes) == 1
        assert lamp.writes[0] == protocol.channel_write_frame(
            (11, 20, 30, 40, 50, 60), swap_cd=True
        )
        await asyncio.sleep(0.32)
        assert len(lamp.writes) == 1
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert len(lamp.writes) == 1

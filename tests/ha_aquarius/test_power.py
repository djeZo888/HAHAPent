"""Native HA power services with actual client and loopback-only synthetic lamp."""

import asyncio
from copy import deepcopy
from unittest.mock import patch

import pytest
import pytest_socket
from custom_components.aquarius_plant_led import protocol
from custom_components.aquarius_plant_led.const import DOMAIN, NAME
from custom_components.aquarius_plant_led.state_store import PowerMemoryError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.aquarius_tcp_helpers import SYNTHETIC_PROFILES, SyntheticLamp

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


@pytest.fixture
def loopback_network(socket_enabled):
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)


@pytest.fixture
async def power_entry(hass, loopback_network):
    lamp = SyntheticLamp()
    # FA replies distinguish a real all-zero vector from an exact E2 FC query echo.
    lamp.channel_operation = 0xFA
    port = await lamp.start()
    entry = MockConfigEntry(domain=DOMAIN, title=NAME, data={"host": "127.0.0.1", "port": port})
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


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


async def power(hass, entry, action):
    await hass.services.async_call(
        "light", action, {"entity_id": entity_id(hass, entry, "light", "power")}, blocking=True
    )


@pytest.mark.parametrize("zero_on_off", (False, True))
async def test_manual_off_reload_on_restores_exact_mix_only_after_explicit_on(
    hass, power_entry, zero_on_off
):
    lamp, entry = power_entry
    original = lamp.channels
    registry = er.async_get(hass)
    identities = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    if zero_on_off:

        def clear_off(frame, response):
            if frame == protocol.mode_frame(8):
                lamp.channels = (0,) * 6
            return response

        lamp.response_override = clear_off
    await power(hass, entry, "turn_off")
    assert lamp.mode == 8
    assert lamp.writes == [protocol.mode_frame(8)]
    assert hass.states.get(entity_id(hass, entry, "light", "power")).state == "off"
    assert hass.states.get(entity_id(hass, entry, "sensor", "mode_status")).state == "off"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.async_refresh()
    assert lamp.writes == [protocol.mode_frame(8)]
    assert identities == {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    await power(hass, entry, "turn_on")
    assert lamp.mode == 1 and lamp.channels == original
    expected = [protocol.mode_frame(8), protocol.mode_frame(1)]
    if zero_on_off:
        expected.extend([protocol.channel_write_frame(original), protocol.mode_frame(1)])
    assert lamp.writes == expected
    assert hass.states.get(entity_id(hass, entry, "light", "power")).state == "on"
    assert (
        hass.states.get(entity_id(hass, entry, "sensor", "mode_status")).state == "manual_override"
    )


async def test_automatic_zero_output_is_on_and_off_on_sends_no_channel_vector(hass, power_entry):
    lamp, entry = power_entry
    lamp.mode, lamp.channels = 0, (0,) * 6
    await entry.runtime_data.async_refresh()
    light = hass.states.get(entity_id(hass, entry, "light", "power"))
    assert light.state == "on"
    assert light.attributes["supported_color_modes"] == ["onoff"]
    assert light.attributes["supported_features"] == 0
    assert "brightness" not in light.attributes and "rgb_color" not in light.attributes
    status = entity_id(hass, entry, "sensor", "mode_status")
    assert hass.states.get(status).state == "following_schedule"
    assert er.async_get(hass).async_get(status).entity_category is None
    await power(hass, entry, "turn_off")
    await power(hass, entry, "turn_on")
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(0)]
    assert lamp.channels == (0,) * 6


async def test_unknown_off_origin_explicit_on_resumes_schedule(hass, power_entry):
    lamp, entry = power_entry
    lamp.mode, lamp.channels = 8, (0,) * 6
    await entry.runtime_data.async_refresh()
    await power(hass, entry, "turn_on")
    assert lamp.writes == [protocol.mode_frame(0)]
    assert lamp.mode == 0 and lamp.channels == (0,) * 6


async def test_future_memory_preserved_while_explicit_on_falls_back_and_off_is_blocked(
    hass, hass_storage, power_entry
):
    lamp, entry = power_entry
    await power(hass, entry, "turn_off")
    key = entry.runtime_data.power_memory.key
    hass_storage[key]["version"] = 2
    future_record = deepcopy(hass_storage[key])
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert lamp.writes == [protocol.mode_frame(8)]
    assert entry.runtime_data.power_memory.error
    await power(hass, entry, "turn_on")
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(0)]
    assert hass_storage[key] == future_record
    with pytest.raises(HomeAssistantError, match="Off was not sent"):
        await power(hass, entry, "turn_off")
    assert hass_storage[key] == future_record
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(0)]


async def test_resume_button_overrides_manual_memory_and_does_not_change_levels(hass, power_entry):
    lamp, entry = power_entry
    await power(hass, entry, "turn_off")
    button = entity_id(hass, entry, "button", "resume_schedule")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert lamp.mode == 0
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(0)]
    lamp.mode = 1
    await entry.runtime_data.async_refresh()
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert lamp.writes[-1] == protocol.mode_frame(0)


async def test_off_memory_failure_prevents_any_mutation(hass, power_entry):
    lamp, entry = power_entry
    with patch.object(entry.runtime_data.power_memory, "_save", side_effect=PowerMemoryError):
        with pytest.raises(HomeAssistantError, match="Off was not sent"):
            await power(hass, entry, "turn_off")
    assert lamp.writes == []
    assert lamp.mode == 1


async def test_cancelled_presave_cannot_turn_off_later(hass, power_entry):
    lamp, entry = power_entry
    memory = entry.runtime_data.power_memory
    started, release = asyncio.Event(), asyncio.Event()
    original = memory._writer.async_save

    async def delayed(data):
        started.set()
        await release.wait()
        await original(data)

    with patch.object(memory._writer, "async_save", delayed):
        task = asyncio.create_task(entry.runtime_data.async_turn_off())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    await entry.runtime_data.async_refresh()
    assert lamp.writes == []
    assert lamp.mode == 1


async def test_unconfirmed_off_stays_pending_and_on_uses_schedule_fallback(hass, power_entry):
    lamp, entry = power_entry
    # Ignore the Off command: echoed bytes cannot count as confirmation.
    lamp.ignore_writes, lamp.echo_writes = True, True
    with pytest.raises(HomeAssistantError, match="Off was not confirmed"):
        await power(hass, entry, "turn_off")
    assert not entry.runtime_data.last_update_success
    lamp.ignore_writes, lamp.echo_writes = False, False
    lamp.mode, lamp.channels = 8, (0,) * 6
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.power_memory.manual_restore(entry.runtime_data.data)[0] is None
    await power(hass, entry, "turn_on")
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(0)]


async def test_separate_power_gate_and_off_origin_number_guard(hass, power_entry):
    lamp, entry = power_entry
    with patch.object(protocol, "VERIFIED_SHUTDOWN_PROFILES", frozenset()):
        with pytest.raises(ServiceValidationError, match="Software On/Off"):
            await power(hass, entry, "turn_off")
    lamp.mode = 8
    await entry.runtime_data.async_refresh()
    with pytest.raises(ServiceValidationError, match="unsupported operating mode"):
        await entry.runtime_data.async_set_channel(0, 11)
    assert lamp.writes == []


async def test_unknown_mode_status_and_primary_light_are_unknown(hass, power_entry):
    lamp, entry = power_entry
    lamp.mode = 254
    await entry.runtime_data.async_refresh()
    assert hass.states.get(entity_id(hass, entry, "sensor", "mode_status")).state == "unknown"
    assert hass.states.get(entity_id(hass, entry, "light", "power")).state == "unknown"
    with pytest.raises(ServiceValidationError, match="unsupported operating mode"):
        await power(hass, entry, "turn_on")
    assert lamp.writes == []


async def test_retained_off_to_unexpected_manual_zero_never_restores_vector(hass, power_entry):
    lamp, entry = power_entry
    await power(hass, entry, "turn_off")

    def unexpected_zero(frame, response):
        if frame == protocol.mode_frame(1):
            lamp.channels = (0,) * 6
        return response

    lamp.response_override = unexpected_zero
    with pytest.raises(HomeAssistantError, match="On was not confirmed"):
        await power(hass, entry, "turn_on")
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(1)]
    await entry.runtime_data.async_refresh()
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(1)]


@pytest.mark.parametrize("interference", ("levels", "profile", "cancel"))
async def test_zero_manual_return_requires_another_fresh_guard_before_saved_vector(
    hass, power_entry, interference
):
    lamp, entry = power_entry

    def zero_off(frame, response):
        if frame == protocol.mode_frame(8):
            lamp.channels = (0,) * 6
        return response

    lamp.response_override = zero_off
    await power(hass, entry, "turn_off")
    manual_reads = 0
    guard_reached = asyncio.Event()
    release_guard = asyncio.Event()

    async def guard(connection, frame):
        nonlocal manual_reads
        if frame == protocol.SYSTEM_QUERY and lamp.mode == 1:
            manual_reads += 1
            # Queried mode barrier, independent full read, then fresh guard.
            if manual_reads == 3:
                guard_reached.set()
                if interference == "levels":
                    lamp.channels = (1, 0, 0, 0, 0, 0)
                elif interference == "profile":
                    lamp.version = (2, 6)
                else:
                    await release_guard.wait()

    lamp.hook = guard
    if interference == "cancel":
        task = asyncio.create_task(entry.runtime_data.async_turn_on())
        await asyncio.wait_for(guard_reached.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release_guard.set()
        await asyncio.sleep(0)
        assert entry.runtime_data.client._active_task is None
        assert entry.runtime_data.client._writer is None
    else:
        with pytest.raises(HomeAssistantError, match="On was not confirmed"):
            await power(hass, entry, "turn_on")
        assert guard_reached.is_set()
    assert not entry.runtime_data.last_update_success
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(1)]
    lamp.hook = None
    await entry.runtime_data.async_refresh()
    assert lamp.writes == [protocol.mode_frame(8), protocol.mode_frame(1)]

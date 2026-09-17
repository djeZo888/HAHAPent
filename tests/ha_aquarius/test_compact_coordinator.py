"""Native HA coordinator compact ordering; every device response is synthetic."""

import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest
from custom_components.aquarius_plant_led.client import AquariusError, CompactInputError
from custom_components.aquarius_plant_led.compact import (
    CONF_CHANNEL_ROLES,
    CONF_CHANNEL_ROLES_VERSION,
    mix_rgb,
    scale_channels,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

ROLES = ("red", "green", "blue", "red", "white", "unused")
OPTIONS = {
    CONF_CHANNEL_ROLES_VERSION: 1,
    CONF_CHANNEL_ROLES: dict(zip((f"channel_{letter}" for letter in "abcdef"), ROLES)),
}
COORDINATOR = "custom_components.aquarius_plant_led.coordinator"


@pytest.fixture
async def compact_entry(hass, config_entry, mock_client, observed_state, verified_profiles):
    hass.config_entries.async_update_entry(config_entry, options=OPTIONS)

    async def compact(**kwargs):
        before = kwargs["expected_state"]
        level = kwargs["intensity"]
        if kwargs["rgb_color"] is not None:
            desired = mix_rgb(kwargs["rgb_color"], level or max(before.channels) or 5, ROLES)
        else:
            basis = kwargs["manual_channels"] if before.system.mode_raw == 8 else before.channels
            desired = scale_channels(basis, level)
        state = replace(before, system=replace(before.system, mode_raw=1), channels=desired)
        mock_client.refresh.side_effect = None
        mock_client.refresh.return_value = state
        return state

    mock_client.set_compact.side_effect = compact
    mock_client.turn_off.return_value = replace(
        observed_state, system=replace(observed_state.system, mode_raw=8), channels=(0,) * 6
    )
    mock_client.turn_on.return_value = observed_state
    with (
        patch(
            "custom_components.aquarius_plant_led.protocol.VERIFIED_SHUTDOWN_PROFILES",
            verified_profiles,
        ),
        patch(f"{COORDINATOR}.CHANNEL_DEBOUNCE_SECONDS", 0.01),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        yield config_entry


async def test_partial_compact_requests_coalesce_without_optimistic_state(
    compact_entry, mock_client
):
    coordinator = compact_entry.runtime_data
    original = coordinator.data
    colour = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 128, 0)))
    await asyncio.sleep(0)
    brightness = asyncio.create_task(coordinator.async_set_compact(intensity=20))
    await asyncio.sleep(0)
    assert coordinator.data is original
    await asyncio.gather(colour, brightness)
    mock_client.set_compact.assert_awaited_once()
    assert mock_client.set_compact.await_args.kwargs["rgb_color"] == (255, 128, 0)
    assert mock_client.set_compact.await_args.kwargs["intensity"] == 20
    assert coordinator.data.channels == (20, 10, 0, 20, 0, 0)
    assert coordinator._pending_compact is None
    assert coordinator.power_memory._record["last_manual"]["channels"] == [20, 10, 0, 20, 0, 0]


async def test_reverse_partial_order_and_latest_values_are_one_intent(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    tasks = []
    for kwargs in ({"intensity": 10}, {"rgb_color": (0, 255, 0)}, {"intensity": 30}):
        tasks.append(asyncio.create_task(coordinator.async_set_compact(**kwargs)))
        await asyncio.sleep(0)
    await asyncio.gather(*tasks)
    mock_client.set_compact.assert_awaited_once()
    assert coordinator.data.channels == (0, 30, 0, 0, 0, 0)


@pytest.mark.parametrize("newer", ("number", "mode", "off", "on"))
async def test_newer_detailed_or_power_action_supersedes_pending_compact(
    compact_entry, mock_client, newer
):
    coordinator = compact_entry.runtime_data
    old = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 0, 0), intensity=20))
    await asyncio.sleep(0)
    if newer == "number":
        await coordinator.async_set_channel(0, 11)
    elif newer == "mode":
        await coordinator.async_set_mode("automatic_program")
    elif newer == "off":
        await coordinator.async_turn_off()
    else:
        await coordinator.async_turn_on()
    await old
    mock_client.set_compact.assert_not_awaited()
    assert coordinator._pending_compact is None


async def test_compact_supersedes_debouncing_number(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    old = asyncio.create_task(coordinator.async_set_channel(0, 11))
    await asyncio.sleep(0)
    await coordinator.async_set_compact(intensity=30)
    await old
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_compact.assert_awaited_once()


async def test_newer_gesture_does_not_cancel_admitted_transaction(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    entered = asyncio.Event()
    release = asyncio.Event()
    apply = mock_client.set_compact.side_effect

    async def block(**kwargs):
        entered.set()
        await release.wait()
        return await apply(**kwargs)

    mock_client.set_compact.side_effect = block
    first = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 0, 0), intensity=20))
    await entered.wait()
    second = asyncio.create_task(coordinator.async_set_compact(intensity=10))
    await asyncio.sleep(0)
    assert not first.done()
    release.set()
    await asyncio.gather(first, second)
    assert mock_client.set_compact.await_count == 2
    assert coordinator.data.channels == (10, 0, 0, 10, 0, 0)


@pytest.mark.parametrize("kwargs", ({"intensity": 0}, {"rgb_color": (0, 0, 0)}))
async def test_zero_uses_existing_durable_off_path(compact_entry, mock_client, kwargs):
    coordinator = compact_entry.runtime_data
    before = coordinator.data.channels
    await coordinator.async_set_compact(**kwargs)
    mock_client.set_compact.assert_not_awaited()
    mock_client.turn_off.assert_awaited_once()
    assert coordinator.power_memory.manual_restore(coordinator.data)[0] == before


async def test_off_passes_only_confirmed_manual_origin_basis(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    original = coordinator.data
    await coordinator.async_turn_off()
    await coordinator.async_set_compact(intensity=20)
    assert mock_client.set_compact.await_args.kwargs["manual_channels"] == original.channels
    assert coordinator.power_memory._record["off_origin"] is None
    assert coordinator.data.system.mode_raw == 1


@pytest.mark.parametrize(
    "kwargs", ({}, {"intensity": True}, {"intensity": 101}, {"rgb_color": (0, 0, float("nan"))})
)
async def test_invalid_inputs_do_not_call_client(compact_entry, mock_client, kwargs):
    with pytest.raises(ServiceValidationError):
        await compact_entry.runtime_data.async_set_compact(**kwargs)
    mock_client.set_compact.assert_not_awaited()
    mock_client.turn_off.assert_not_awaited()


async def test_missing_role_options_refuses_compact(loaded_entry, mock_client):
    with pytest.raises(ServiceValidationError, match="Configure"):
        await loaded_entry.runtime_data.async_set_compact(intensity=20)
    mock_client.set_compact.assert_not_awaited()


async def test_no_basis_error_is_clear_and_sends_no_power_fallback(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    original = mock_client.set_compact.side_effect
    fresh = replace(coordinator.data, channels=(0,) * 6)
    mock_client.set_compact.side_effect = CompactInputError("Choose a colour first", fresh)
    with pytest.raises(ServiceValidationError, match="Choose a colour first"):
        await coordinator.async_set_compact(intensity=20)
    mock_client.turn_on.assert_not_awaited()
    mock_client.turn_off.assert_not_awaited()
    assert coordinator.last_update_success
    assert coordinator.data == fresh
    assert coordinator._failures == 0
    assert coordinator._pending_compact is None
    mock_client.set_compact.assert_awaited_once()
    mock_client.set_compact.side_effect = original
    await coordinator.async_set_compact(rgb_color=(255, 0, 0), intensity=10)
    assert mock_client.set_compact.await_count == 2


async def test_no_basis_discards_older_queued_compact_but_allows_a_new_choice(
    compact_entry, mock_client
):
    coordinator = compact_entry.runtime_data
    entered = asyncio.Event()
    release = asyncio.Event()
    original = mock_client.set_compact.side_effect
    fresh = replace(coordinator.data, channels=(0,) * 6)

    async def no_basis(**kwargs):
        entered.set()
        await release.wait()
        raise CompactInputError("Choose a colour first", fresh)

    mock_client.set_compact.side_effect = no_basis
    first = asyncio.create_task(coordinator.async_set_compact(intensity=20))
    await entered.wait()
    queued = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 0, 0)))
    await asyncio.sleep(0)
    release.set()
    result = await asyncio.gather(first, queued, return_exceptions=True)
    assert isinstance(result[0], ServiceValidationError)
    assert isinstance(result[1], HomeAssistantError)
    assert coordinator.last_update_success
    assert coordinator._pending_compact is None
    mock_client.set_compact.assert_awaited_once()
    mock_client.set_compact.side_effect = original
    await coordinator.async_set_compact(rgb_color=(0, 255, 0), intensity=10)
    assert coordinator.data.channels == (0, 10, 0, 0, 0, 0)


async def test_roles_changed_while_debouncing_abort_before_client(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    with patch(f"{COORDINATOR}.compact_roles_from_options", side_effect=[ROLES, None]):
        with pytest.raises(ServiceValidationError, match="Channel roles changed"):
            await coordinator.async_set_compact(intensity=10)
    mock_client.set_compact.assert_not_awaited()
    assert coordinator._pending_compact is None


async def test_failure_discards_pending_recipe_and_prevents_replay_after_read(
    compact_entry, mock_client
):
    coordinator = compact_entry.runtime_data
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fail(**kwargs):
        entered.set()
        await release.wait()
        raise AquariusError("synthetic lost readback")

    mock_client.set_compact.side_effect = fail
    first = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 0, 0), intensity=20))
    await entered.wait()
    second = asyncio.create_task(coordinator.async_set_compact(intensity=10))
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(result, HomeAssistantError) for result in results)
    assert coordinator._pending_compact is None
    await coordinator.async_refresh()
    mock_client.set_compact.assert_awaited_once()
    assert coordinator.last_update_success


async def test_deadline_includes_debounce_and_clears_intent(compact_entry, mock_client):
    coordinator = compact_entry.runtime_data
    with patch(f"{COORDINATOR}.EXPLICIT_COMMAND_TIMEOUT", 0.001):
        with pytest.raises(HomeAssistantError, match="expired"):
            await coordinator.async_set_compact(intensity=10)
    mock_client.set_compact.assert_not_awaited()
    assert coordinator._pending_compact is None
    assert not coordinator.last_update_success


async def test_unload_cancels_admitted_compact_and_clears_pending_recipe(
    hass, compact_entry, mock_client
):
    coordinator = compact_entry.runtime_data
    entered = asyncio.Event()

    async def stall(**kwargs):
        entered.set()
        await asyncio.Future()

    mock_client.set_compact.side_effect = stall
    action = asyncio.create_task(coordinator.async_set_compact(rgb_color=(255, 0, 0)))
    await entered.wait()
    assert await hass.config_entries.async_unload(compact_entry.entry_id)
    with pytest.raises(asyncio.CancelledError):
        await action
    assert coordinator._pending_compact is None
    assert coordinator._active_command is None
    mock_client.set_compact.assert_awaited_once()

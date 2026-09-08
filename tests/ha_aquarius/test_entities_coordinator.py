"""Real native entities, services, registry and lifecycle with synthetic transport."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from custom_components.aquarius_plant_led.client import AquariusError
from custom_components.aquarius_plant_led.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


async def test_native_device_six_sliders_diagnostics_and_readonly_lifecycle(
    hass, loaded_entry, mock_client, observed_state
):
    entries = er.async_entries_for_config_entry(er.async_get(hass), loaded_entry.entry_id)
    numbers = [entry for entry in entries if entry.domain == "number"]
    assert len(numbers) == 6
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)
    assert len(devices) == 1
    assert devices[0].identifiers == {(DOMAIN, loaded_entry.entry_id)}
    assert devices[0].sw_version is None
    assert devices[0].serial_number is None
    for index, channel in enumerate("abcdef"):
        state = hass.states.get(entity_id(hass, loaded_entry, "number", f"channel_{channel}"))
        assert float(state.state) == observed_state.channels[index]
        assert state.attributes["min"] == 0
        assert state.attributes["max"] == 100
        assert state.attributes["step"] == 1
        assert state.attributes["mode"] == "slider"
        assert state.attributes["unit_of_measurement"] == "%"
        assert "manual" in state.attributes["adjustment_action"]
    assert (
        hass.states.get(entity_id(hass, loaded_entry, "select", "operating_mode")).state == "manual"
    )
    raw = hass.states.get(entity_id(hass, loaded_entry, "sensor", "raw_version_bytes"))
    assert raw.state == "01 02"
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()
    assert mock_client.close.await_count >= 2


@pytest.mark.parametrize("index", range(6))
async def test_each_native_number_service_sets_one_channel_using_observed_state(
    hass, loaded_entry, mock_client, observed_state, index
):
    target = entity_id(hass, loaded_entry, "number", f"channel_{'abcdef'[index]}")
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": target, "value": 42}, blocking=True
        )
    mock_client.set_channel.assert_awaited_once_with(index, 42, expected_state=observed_state)
    assert hass.states.get(target).state == "42"
    assert all(
        value == (42 if other == index else observed_state.channels[other])
        for other, value in enumerate(loaded_entry.runtime_data.data.channels)
    )


@pytest.mark.parametrize("value", [-1, 101, 1.5, float("nan"), float("inf")])
async def test_invalid_slider_service_values_do_not_write(hass, loaded_entry, mock_client, value):
    target = entity_id(hass, loaded_entry, "number", "channel_a")
    with pytest.raises((HomeAssistantError, ValueError)):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": target, "value": value}, blocking=True
        )
    mock_client.set_channel.assert_not_awaited()


async def test_explicit_automatic_select_uses_protocol_zero(hass, loaded_entry, mock_client):
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id(hass, loaded_entry, "select", "operating_mode"),
            "option": "automatic_program",
        },
        blocking=True,
    )
    assert mock_client.set_mode.await_args.args == (0,)
    assert loaded_entry.runtime_data.data.system.mode_raw == 0
    mock_client.set_channel.assert_not_awaited()


async def test_unknown_mode_is_preserved_without_claiming_manual_or_automatic(hass, loaded_entry):
    coordinator = loaded_entry.runtime_data
    coordinator.async_set_updated_data(
        replace(coordinator.data, system=replace(coordinator.data.system, mode_raw=77))
    )
    assert (
        hass.states.get(entity_id(hass, loaded_entry, "select", "operating_mode")).state
        == "unknown"
    )
    assert hass.states.get(entity_id(hass, loaded_entry, "sensor", "raw_mode")).state == "77"


async def test_disconnect_unavailable_backoff_then_readonly_recovery(
    hass, loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    previous = coordinator.data
    mock_client.refresh.side_effect = AquariusError("Synthetic offline")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == timedelta(seconds=60)
    assert (
        hass.states.get(entity_id(hass, loaded_entry, "number", "channel_a")).state == "unavailable"
    )
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=120)
    mock_client.refresh.side_effect = None
    mock_client.refresh.return_value = previous
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.update_interval == timedelta(seconds=30)
    assert hass.states.get(entity_id(hass, loaded_entry, "number", "channel_a")).state == "10"
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


async def test_command_failure_never_optimistically_updates_or_retries(
    hass, loaded_entry, mock_client, observed_state
):
    coordinator = loaded_entry.runtime_data
    mock_client.set_channel.side_effect = AquariusError("Synthetic uncertain readback")
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        with pytest.raises(HomeAssistantError, match="No command was retried"):
            await coordinator.async_set_channel(0, 15)
        assert coordinator.data == observed_state
        assert not coordinator.last_update_success
        with pytest.raises(HomeAssistantError, match="successful controller read"):
            await coordinator.async_set_channel(0, 15)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    mock_client.set_channel.assert_awaited_once()


async def test_slider_burst_debounces_to_latest_value(loaded_entry, mock_client):
    coordinator = loaded_entry.runtime_data
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.01):
        await asyncio.gather(*(coordinator.async_set_channel(0, value) for value in (11, 12, 13)))
    assert mock_client.set_channel.await_count == 1
    assert mock_client.set_channel.await_args.args == (0, 13)
    assert coordinator.data.channels[0] == 13


async def test_native_action_deadline_includes_debounce_and_never_replays(
    hass, loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    epoch = coordinator._command_epoch
    with (
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.06),
        patch("custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.02),
    ):
        with pytest.raises(HomeAssistantError, match="expired before completion"):
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id(hass, loaded_entry, "number", "channel_a"), "value": 11},
                blocking=True,
            )
        await asyncio.sleep(0.08)
    assert coordinator._command_epoch == epoch + 1
    assert not coordinator.last_update_success
    mock_client.set_channel.assert_not_awaited()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    mock_client.set_channel.assert_not_awaited()


@pytest.mark.parametrize("action", ("channel", "mode"))
async def test_action_waiting_behind_poll_expires_and_cannot_write_after_poll_recovers(
    loaded_entry, mock_client, observed_state, action
):
    coordinator = loaded_entry.runtime_data
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_poll():
        entered.set()
        await release.wait()
        return observed_state

    mock_client.refresh.side_effect = slow_poll
    poll = asyncio.create_task(coordinator.async_refresh())
    await entered.wait()
    with (
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0),
        patch("custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.02),
    ):
        with pytest.raises(HomeAssistantError, match="expired before completion"):
            await (
                coordinator.async_set_channel(0, 11)
                if action == "channel"
                else coordinator.async_set_mode("automatic_program")
            )
    release.set()
    await poll
    await asyncio.sleep(0)
    assert coordinator.last_update_success
    assert coordinator._active_command is None
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize("action", ("channel", "mode"))
async def test_action_deadline_awaits_client_cancellation_cleanup_before_returning(
    loaded_entry, mock_client, action
):
    coordinator = loaded_entry.runtime_data
    settled = asyncio.Event()

    async def slow_command(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.01)
            settled.set()

    command = mock_client.set_channel if action == "channel" else mock_client.set_mode
    command.side_effect = slow_command
    with (
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0),
        patch("custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.02),
    ):
        with pytest.raises(HomeAssistantError, match="expired before completion"):
            await (
                coordinator.async_set_channel(0, 11)
                if action == "channel"
                else coordinator.async_set_mode("automatic_program")
            )
    assert settled.is_set()
    assert coordinator._active_command is None
    assert not coordinator.last_update_success
    command.assert_awaited_once()


async def test_expired_queued_action_does_not_clear_another_actions_active_task(
    loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    entered = asyncio.Event()

    async def active_command(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    mock_client.set_channel.side_effect = active_command
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        active = asyncio.create_task(coordinator.async_set_channel(0, 11))
        await entered.wait()
        with patch(
            "custom_components.aquarius_plant_led.coordinator.EXPLICIT_COMMAND_TIMEOUT", 0.02
        ):
            with pytest.raises(HomeAssistantError, match="expired before completion"):
                await coordinator.async_set_mode("automatic_program")
        assert coordinator._active_command is active
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
    assert coordinator._active_command is None
    mock_client.set_mode.assert_not_awaited()


async def test_mode_choice_supersedes_pending_slider(loaded_entry, mock_client):
    coordinator = loaded_entry.runtime_data
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.01):
        task = asyncio.create_task(coordinator.async_set_channel(0, 15))
        await asyncio.sleep(0)
        await coordinator.async_set_mode("automatic_program")
        await task
    mock_client.set_channel.assert_not_awaited()
    assert mock_client.set_mode.await_args.args == (0,)


async def test_unload_prevents_pending_slider_write(hass, loaded_entry, mock_client):
    coordinator = loaded_entry.runtime_data
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.01):
        task = asyncio.create_task(coordinator.async_set_channel(0, 15))
        await asyncio.sleep(0)
        assert await hass.config_entries.async_unload(loaded_entry.entry_id)
        with pytest.raises(HomeAssistantError, match="successful controller read"):
            await task
    mock_client.set_channel.assert_not_awaited()


async def test_initial_offline_setup_retries_without_writes(hass, config_entry, mock_client):
    mock_client.refresh.side_effect = AquariusError("Synthetic offline")
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()
    mock_client.close.assert_awaited()


@pytest.mark.parametrize("queued_action", ("channel", "mode"))
async def test_old_queued_command_does_not_replay_after_fault_and_poll_recovery(
    loaded_entry, mock_client, queued_action
):
    coordinator = loaded_entry.runtime_data
    entered = asyncio.Event()
    fail_now = asyncio.Event()

    async def fail_after_queueing(*args, **kwargs):
        entered.set()
        await fail_now.wait()
        raise AquariusError("Synthetic uncertain command")

    mock_client.set_channel.side_effect = fail_after_queueing
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        first = asyncio.create_task(coordinator.async_set_channel(0, 11))
        await entered.wait()
        # Lock ordering is deliberate: failed command, successful poll, old action.
        recovery = asyncio.create_task(coordinator.async_refresh())
        await asyncio.sleep(0)
        old_action = asyncio.create_task(
            coordinator.async_set_channel(1, 22)
            if queued_action == "channel"
            else coordinator.async_set_mode("automatic_program")
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        fail_now.set()
        with pytest.raises(HomeAssistantError, match="No command was retried"):
            await first
        await recovery
        assert coordinator.last_update_success
        with pytest.raises(HomeAssistantError, match="changed after this request"):
            await old_action
    mock_client.set_channel.assert_awaited_once()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize("action", ("channel", "mode"))
async def test_cancelled_inflight_command_marks_output_unavailable_without_retry(
    hass, loaded_entry, mock_client, action
):
    coordinator = loaded_entry.runtime_data
    entered = asyncio.Event()

    async def uncertain_command(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    command = mock_client.set_channel if action == "channel" else mock_client.set_mode
    command.side_effect = uncertain_command
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        pending = asyncio.create_task(
            coordinator.async_set_channel(0, 11)
            if action == "channel"
            else coordinator.async_set_mode("automatic_program")
        )
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert not coordinator.last_update_success
    assert (
        hass.states.get(entity_id(hass, loaded_entry, "number", "channel_a")).state == "unavailable"
    )
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    command.assert_awaited_once()


async def test_slow_platform_unload_blocks_pending_and_new_commands(
    hass, loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    started = asyncio.Event()
    finish = asyncio.Event()
    original_unload = hass.config_entries.async_unload_platforms

    async def slow_unload(*args):
        started.set()
        await finish.wait()
        return await original_unload(*args)

    with (
        patch.object(hass.config_entries, "async_unload_platforms", side_effect=slow_unload),
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.01),
    ):
        old_action = asyncio.create_task(coordinator.async_set_channel(0, 11))
        await asyncio.sleep(0)
        unload = asyncio.create_task(hass.config_entries.async_unload(loaded_entry.entry_id))
        await started.wait()
        with pytest.raises(HomeAssistantError, match="successful controller read"):
            await old_action
        with pytest.raises(HomeAssistantError, match="successful controller read"):
            await coordinator.async_set_mode("automatic_program")
        mock_client.set_channel.assert_not_awaited()
        mock_client.set_mode.assert_not_awaited()
        finish.set()
        assert await unload


async def test_failed_unload_reads_before_resuming_and_does_not_revive_old_action(
    hass, loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    reads = mock_client.refresh.await_count
    with (
        patch.object(hass.config_entries, "async_unload_platforms", return_value=False),
        patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0.01),
    ):
        old_action = asyncio.create_task(coordinator.async_set_channel(0, 11))
        await asyncio.sleep(0)
        assert not await hass.config_entries.async_unload(loaded_entry.entry_id)
        assert loaded_entry.state is ConfigEntryState.FAILED_UNLOAD
        assert mock_client.refresh.await_count == reads + 1
        assert coordinator.last_update_success
        with pytest.raises(HomeAssistantError, match="changed after this request"):
            await old_action
    mock_client.set_channel.assert_not_awaited()
    await coordinator.async_set_channel(0, 12)
    mock_client.set_channel.assert_awaited_once()
    # HA marks failed unloads non-recoverable; clean the still-live platforms
    # explicitly without pretending the native entry was restored to LOADED.
    from custom_components.aquarius_plant_led import async_unload_entry

    assert await async_unload_entry(hass, loaded_entry)


async def test_unload_cancels_active_command_before_unloading_platforms(
    hass, loaded_entry, mock_client
):
    coordinator = loaded_entry.runtime_data
    entered = asyncio.Event()
    original_unload = hass.config_entries.async_unload_platforms

    async def stalled_command(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    async def checked_platform_unload(*args):
        assert pending.cancelled()
        assert not coordinator.last_update_success
        return await original_unload(*args)

    mock_client.set_channel.side_effect = stalled_command
    with patch("custom_components.aquarius_plant_led.coordinator.CHANNEL_DEBOUNCE_SECONDS", 0):
        pending = asyncio.create_task(coordinator.async_set_channel(0, 11))
        await entered.wait()
        with patch.object(
            hass.config_entries, "async_unload_platforms", side_effect=checked_platform_unload
        ):
            assert await hass.config_entries.async_unload(loaded_entry.entry_id)
        with pytest.raises(asyncio.CancelledError):
            await pending
    mock_client.set_channel.assert_awaited_once()
    mock_client.set_mode.assert_not_awaited()


@pytest.mark.parametrize("verified_profiles", [frozenset()])
async def test_unvalidated_profile_reports_levels_and_clearly_blocks_all_native_controls(
    hass, loaded_entry, mock_client, observed_state
):
    coordinator = loaded_entry.runtime_data
    reads = mock_client.refresh.await_count
    support = hass.states.get(entity_id(hass, loaded_entry, "sensor", "write_support"))
    assert support.state == "read_only"
    for index, channel in enumerate("abcdef"):
        target = entity_id(hass, loaded_entry, "number", f"channel_{channel}")
        state = hass.states.get(target)
        assert int(state.state) == observed_state.channels[index]
        assert state.attributes["adjustment_action"].startswith("Read-only")
        with pytest.raises(ServiceValidationError, match="controller profile is read-only"):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": target, "value": 42}, blocking=True
            )
    for option in ("manual", "automatic_program"):
        with pytest.raises(ServiceValidationError, match="controller profile is read-only"):
            await hass.services.async_call(
                "select",
                "select_option",
                {
                    "entity_id": entity_id(hass, loaded_entry, "select", "operating_mode"),
                    "option": option,
                },
                blocking=True,
            )
    assert coordinator.last_update_success
    assert coordinator.data == observed_state
    assert mock_client.refresh.await_count == reads
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()

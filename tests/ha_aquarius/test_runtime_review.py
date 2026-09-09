"""Independent native lifecycle regressions using fictional device observations."""

import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("operation", ("reload", "remove"))
async def test_lifecycle_settles_observation_save_before_replacing_coordinator(
    hass, loaded_entry, mock_client, observed_state, hass_storage, operation
):
    """A prior poll cannot retain a writer after a new entry instance starts."""
    coordinator = loaded_entry.runtime_data
    mock_client.refresh.side_effect = None
    mock_client.refresh.return_value = replace(observed_state, channels=(11, 20, 30, 40, 50, 60))
    started, release = asyncio.Event(), asyncio.Event()
    original_save = coordinator.power_memory._writer.async_save

    async def delayed_save(record):
        started.set()
        await release.wait()
        await original_save(record)

    with patch.object(coordinator.power_memory._writer, "async_save", delayed_save):
        # An explicitly requested coordinator refresh may run outside the
        # config entry's background-task registry (as native entity refreshes do).
        polling = asyncio.create_task(coordinator.async_request_refresh())
        await asyncio.wait_for(started.wait(), 1)
        lifecycle = (
            hass.config_entries.async_reload if operation == "reload"
            else hass.config_entries.async_remove
        )
        reloading = asyncio.create_task(lifecycle(loaded_entry.entry_id))
        try:
            done, _pending = await asyncio.wait((reloading,), timeout=0.2)
            assert not done, "lifecycle completed while the previous observation writer was pending"
        finally:
            release.set()
            results = await asyncio.gather(polling, reloading, return_exceptions=True)
    if operation == "reload":
        assert results[1] is True
        assert loaded_entry.runtime_data is not coordinator
    else:
        assert results[1] == {"require_restart": False}
        assert hass.config_entries.async_get_entry(loaded_entry.entry_id) is None
        assert coordinator.power_memory.key not in hass_storage
    mock_client.turn_off.assert_not_awaited()
    mock_client.turn_on.assert_not_awaited()
    mock_client.set_channel.assert_not_awaited()
    mock_client.set_mode.assert_not_awaited()

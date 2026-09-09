"""Native HA storage safety tests; all records and controller replies are synthetic."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from custom_components.aquarius_plant_led.state_store import (
    NO_MANUAL_STATE,
    AquariusPowerMemory,
    PowerMemoryError,
    _PowerStore,
)
from homeassistant.helpers import storage
from homeassistant.util.file import WriteError

# Capture the real storage methods before HA's per-test mock_storage fixture.
REAL_LOAD = storage.Store._async_load
REAL_WRITE = storage.Store._async_write_data


@pytest.fixture
def hass_config_dir(tmp_path):
    """Actual power files must be isolated per test, not shared fixture assets."""
    return str(tmp_path)


@pytest.fixture
def actual_power_storage():
    """Use real HA serialization, file IO and swallowed WriteError handling."""
    with (
        patch.object(_PowerStore, "_async_load", REAL_LOAD),
        patch.object(_PowerStore, "_async_write_data", REAL_WRITE),
    ):
        yield


def off_state(state, channels=None):
    return replace(
        state,
        system=replace(state.system, mode_raw=8),
        channels=state.channels if channels is None else channels,
    )


async def test_confirmed_manual_mix_survives_fresh_storage_instance(hass, observed_state):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_load()
    await memory.async_observe(observed_state)
    await memory.async_prepare_off(observed_state)
    off = off_state(observed_state, (0,) * 6)
    assert memory.manual_restore(off) == (None, NO_MANUAL_STATE)
    await memory.async_confirm_off(off)
    reloaded = AquariusPowerMemory(hass, "synthetic")
    await reloaded.async_load()
    assert reloaded.manual_restore(off)[0] == observed_state.channels
    await reloaded.async_observe(off)
    assert reloaded.manual_restore(off)[0] == observed_state.channels


async def test_last_nonzero_mix_and_external_on_invalidate_old_off(hass, observed_state):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_observe(observed_state)
    zero = replace(observed_state, channels=(0,) * 6)
    await memory.async_observe(zero)
    await memory.async_prepare_off(zero)
    off = off_state(zero)
    await memory.async_confirm_off(off)
    assert memory.manual_restore(off)[0] == observed_state.channels
    automatic = replace(zero, system=replace(zero.system, mode_raw=0))
    await memory.async_observe(automatic)
    assert memory.manual_restore(off) == (None, NO_MANUAL_STATE)


async def test_unconfirmed_or_mismatched_origin_cannot_restore_manual(hass, observed_state):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_prepare_off(observed_state)
    off = off_state(observed_state)
    await memory.async_observe(off)
    assert memory.manual_restore(off) == (None, NO_MANUAL_STATE)
    await memory.async_confirm_off(off)
    other = replace(off, system=replace(off.system, version_bytes=(1, 3)))
    assert memory.manual_restore(other) == (None, NO_MANUAL_STATE)
    assert memory.manual_restore(replace(off, channels=(0,) * 6)) == (None, NO_MANUAL_STATE)


@pytest.mark.parametrize(
    "corruption", ("future_major", "future_minor", "future_schema", "bool", "profile")
)
async def test_incompatible_record_is_preserved_and_off_saving_blocked(
    hass, hass_storage, observed_state, corruption
):
    initial = AquariusPowerMemory(hass, "synthetic")
    await initial.async_prepare_off(observed_state)
    off = off_state(observed_state)
    await initial.async_confirm_off(off)
    raw = hass_storage[initial.key]
    if corruption == "future_major":
        raw["version"] = 2
    elif corruption == "future_minor":
        raw["minor_version"] = 2
    elif corruption == "future_schema":
        raw["data"]["schema_version"] = 2
    elif corruption == "bool":
        raw["data"]["off_origin"]["mode"] = True
    else:
        raw["data"]["last_manual"]["profile"]["count"] = 5
    untouched = deepcopy(raw)
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_load()
    assert memory.error
    assert memory.manual_restore(off) == (None, NO_MANUAL_STATE)
    for action in (memory.async_observe, memory.async_prepare_off):
        with pytest.raises(PowerMemoryError, match="preserved"):
            await action(observed_state)
    assert hass_storage[initial.key] == untouched


async def test_actual_disk_write_failure_is_not_mistaken_for_saved_intent(
    hass, observed_state, actual_power_storage
):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_load()
    await memory.async_observe(observed_state)
    path = Path(memory._writer.path)
    original = await hass.async_add_executor_job(path.read_bytes)
    # This is the actual HA Store handler: WriteError is logged and swallowed.
    # Only independent durable readback distinguishes it from successful save.
    with patch.object(storage, "write_utf8_file_atomic", side_effect=WriteError("synthetic")):
        with pytest.raises(PowerMemoryError, match="verified"):
            await memory.async_prepare_off(observed_state)
    assert memory.error
    assert await hass.async_add_executor_job(path.read_bytes) == original
    assert memory.manual_restore(off_state(observed_state)) == (None, NO_MANUAL_STATE)
    # A later explicit retry of persistence can succeed; no lamp action occurs here.
    await memory.async_prepare_off(observed_state)
    changed = json.loads(await hass.async_add_executor_job(path.read_text))
    assert changed["data"]["off_origin"]["confirmed"] is False
    assert changed["data"]["revision"] != json.loads(original)["data"]["revision"]


@pytest.mark.parametrize(
    ("field", "value"),
    (("version", 2), ("version", True), ("version", 1.0), ("minor_version", True)),
)
async def test_actual_incompatible_storage_file_is_not_rewritten(
    hass, observed_state, actual_power_storage, field, value
):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_observe(observed_state)
    path = Path(memory._writer.path)
    raw = json.loads(await hass.async_add_executor_job(path.read_text))
    raw[field] = value
    contents = json.dumps(raw)
    await hass.async_add_executor_job(path.write_text, contents)
    fresh = AquariusPowerMemory(hass, "synthetic")
    await fresh.async_load()
    with pytest.raises(PowerMemoryError, match="preserved"):
        await fresh.async_prepare_off(observed_state)
    assert await hass.async_add_executor_job(path.read_text) == contents


@pytest.mark.parametrize("contents", ("{broken", "{}", "[]"))
async def test_actual_corrupt_file_is_preserved_and_blocks_off(
    hass, observed_state, actual_power_storage, contents
):
    memory = AquariusPowerMemory(hass, "synthetic")
    await memory.async_observe(observed_state)
    path = Path(memory._writer.path)
    await hass.async_add_executor_job(path.write_text, contents)
    fresh = AquariusPowerMemory(hass, "synthetic")
    await fresh.async_load()
    assert fresh.error
    assert fresh.manual_restore(off_state(observed_state)) == (None, NO_MANUAL_STATE)
    with pytest.raises(PowerMemoryError, match="preserved"):
        await fresh.async_prepare_off(observed_state)
    assert await hass.async_add_executor_job(path.read_text) == contents


async def test_cancelled_save_settles_before_releasing_intent(hass, observed_state):
    memory = AquariusPowerMemory(hass, "synthetic")
    started, release = asyncio.Event(), asyncio.Event()
    original = memory._writer.async_save

    async def delayed(data):
        started.set()
        await release.wait()
        await original(data)

    with patch.object(memory._writer, "async_save", delayed):
        task = asyncio.create_task(memory.async_prepare_off(observed_state))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert memory.error
    assert memory.manual_restore(off_state(observed_state)) == (None, NO_MANUAL_STATE)
    fresh = AquariusPowerMemory(hass, "synthetic")
    await fresh.async_load()
    assert fresh.manual_restore(off_state(observed_state)) == (None, NO_MANUAL_STATE)


async def test_removal_deletes_only_own_entry_memory(hass, hass_storage, observed_state):
    first, second = AquariusPowerMemory(hass, "first"), AquariusPowerMemory(hass, "second")
    await first.async_observe(observed_state)
    await second.async_observe(observed_state)
    await first.async_remove()
    assert first.key not in hass_storage
    assert second.key in hass_storage

"""Actual HA 2026.9.1 fixtures with synthetic replies and isolated transport."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Exercise the distributable integration exactly where HA expects to import it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "modules/aquarius_plant_led"))

from custom_components.aquarius_plant_led.client import AquariusClient, DeviceState  # noqa: E402
from custom_components.aquarius_plant_led.const import DOMAIN, NAME  # noqa: E402
from custom_components.aquarius_plant_led.protocol import SystemReply  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_custom_components(enable_custom_integrations):
    """Load the shipped custom integration using the real HA component loader."""


@pytest.fixture
def verified_profiles():
    """Enable only a fictional profile inside synthetic action tests."""
    return frozenset({((3, 4), (1, 2), 6)})


@pytest.fixture
def observed_state(verified_profiles):
    with patch(
        "custom_components.aquarius_plant_led.protocol.VERIFIED_WRITE_PROFILES", verified_profiles
    ):
        yield DeviceState(SystemReply(1, (1, 2), (3, 4), 6, 6, False), (10, 20, 30, 40, 50, 60))


@pytest.fixture
def mock_client(observed_state):
    client = AsyncMock(spec=AquariusClient)
    current = observed_state

    async def refresh():
        return current

    async def set_channel(index, value, expected_state=None):
        nonlocal current
        channels = list(current.channels)
        channels[index] = value
        current = replace(
            current, channels=tuple(channels), system=replace(current.system, mode_raw=1)
        )
        return current

    async def set_mode(mode, expected_state=None):
        nonlocal current
        current = replace(current, system=replace(current.system, mode_raw=mode))
        return current

    client.refresh.side_effect = refresh
    client.set_channel.side_effect = set_channel
    client.set_mode.side_effect = set_mode
    with (
        patch("custom_components.aquarius_plant_led.AquariusClient", return_value=client),
        patch(
            "custom_components.aquarius_plant_led.config_flow.AquariusClient", return_value=client
        ),
    ):
        yield client


@pytest.fixture
def config_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={"host": "lamp.example.invalid", "port": 8080},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded_entry(hass, config_entry, mock_client):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry

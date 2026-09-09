"""Native Home Assistant lifecycle for Aquarius Plant LED."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .client import AquariusClient
from .const import DEFAULT_PORT
from .coordinator import AquariusCoordinator
from .state_store import AquariusPowerMemory

PLATFORMS = (Platform.LIGHT, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.BUTTON)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Read current controller state before creating entities; never restore output."""
    client = AquariusClient(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = AquariusCoordinator(hass, entry, client)
    try:
        await coordinator.async_load_power_memory()
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_shutdown()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove native entities and close connections without changing the lamp."""
    coordinator = entry.runtime_data
    await coordinator.async_prepare_unload()
    try:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except Exception:
        await coordinator.async_resume_after_failed_unload()
        raise
    if not unloaded:
        await coordinator.async_resume_after_failed_unload()
        return False
    await coordinator.async_shutdown()
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Do not guess how to downgrade an entry created by a future release."""
    return entry.version == 1 and entry.minor_version == 1


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove only this integration's own power memory after native entry deletion."""
    await AquariusPowerMemory(hass, entry.entry_id).async_remove()

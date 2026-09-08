"""Explicit manual / existing automatic-program mode selection."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODE_OPTIONS
from .entity import AquariusEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AquariusMode(entry.runtime_data)])


class AquariusMode(AquariusEntity, SelectEntity):
    """Resume the controller's stored program without reading or editing its schedule."""

    _attr_translation_key = "operating_mode"
    _attr_options = list(MODE_OPTIONS)
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "operating_mode")

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.data.system.mode_raw
        return next((option for option, value in MODE_OPTIONS.items() if value == raw), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(option)

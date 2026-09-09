"""Logical software power; no RGB or synthetic master brightness."""

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquariusEntity
from .protocol import MODE_AUTOMATIC, MODE_MANUAL, MODE_SHUTDOWN

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AquariusPower(entry.runtime_data)])


class AquariusPower(AquariusEntity, LightEntity):
    """An enabled schedule is On even when its current output is zero."""

    _attr_translation_key = "power"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        mode = self.coordinator.data.system.mode_raw
        if mode == MODE_SHUTDOWN:
            return False
        return True if mode in (MODE_AUTOMATIC, MODE_MANUAL) else None

    @property
    def extra_state_attributes(self) -> dict:
        _channels, reason = self.coordinator.power_memory.manual_restore(self.coordinator.data)
        return {
            "power_control_validated": self.coordinator.data.system.power_supported,
            "on_behavior": reason,
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_turn_off()

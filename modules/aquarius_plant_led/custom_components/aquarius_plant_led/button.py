"""An explicit return to the controller's existing automatic schedule."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquariusEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AquariusResumeSchedule(entry.runtime_data)])


class AquariusResumeSchedule(AquariusEntity, ButtonEntity):
    """Pressing is deliberate; restoring the last-pressed timestamp sends nothing."""

    _attr_translation_key = "resume_schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "resume_schedule")

    async def async_press(self) -> None:
        await self.coordinator.async_turn_on(resume_schedule=True)

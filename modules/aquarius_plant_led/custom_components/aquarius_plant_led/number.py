"""Six independent, native, renameable percentage channel controls."""

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHANNEL_KEYS, CHANNEL_LABELS, channel_labels_from_options
from .coordinator import AquariusCoordinator
from .entity import AquariusEntity
from .protocol import SUPPORTED_CONTROL_MODES

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        AquariusChannel(entry.runtime_data, index) for index in range(len(CHANNEL_LABELS))
    )


class AquariusChannel(AquariusEntity, NumberEntity):
    """Changing a slider deliberately enters and saves manual output."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:led-strip-variant"

    def __init__(self, coordinator: AquariusCoordinator, index: int) -> None:
        super().__init__(coordinator, f"channel_{CHANNEL_LABELS[index].lower()}")
        self._index = index
        label = channel_labels_from_options(coordinator.config_entry.options)[CHANNEL_KEYS[index]]
        self._attr_name = (
            label if label == f"Channel {CHANNEL_LABELS[index]}" else f"{label} intensity"
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.data.channels[self._index]

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data.system.write_supported:
            action = "Read-only: controller profile is not validated for writes"
        elif self.coordinator.data.system.mode_raw not in SUPPORTED_CONTROL_MODES:
            action = "Read-only: the current operating mode is unsupported"
        else:
            action = "Sets and saves manual output; pauses the automatic program"
        return {"protocol_channel": CHANNEL_LABELS[self._index], "adjustment_action": action}

    async def async_set_native_value(self, value: float) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or value != int(value)
            or not 0 <= value <= 100
        ):
            raise ServiceValidationError("Channel level must be an integer from 0 to 100")
        await self.coordinator.async_set_channel(self._index, int(value))

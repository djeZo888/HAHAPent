"""Honest diagnostic protocol fields, including unrecognized raw modes."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AquariusEntity

PARALLEL_UPDATES = 0
DIAGNOSTICS = {
    "mode_status": "Mode status",
    "write_support": "Write support",
    "raw_mode": "Raw mode",
    "raw_version_bytes": "Raw version bytes",
    "raw_controller_bytes": "Raw controller bytes",
    "raw_channel_count": "Raw channel count",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(AquariusDiagnostic(entry.runtime_data, key) for key in DIAGNOSTICS)


class AquariusDiagnostic(AquariusEntity, SensorEntity):
    """Expose raw replies without inventing a model, serial, or firmware version."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._key = key
        if key == "mode_status":
            self._attr_entity_category = None
        if key in ("write_support", "mode_status"):
            self._attr_translation_key = key
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = (
                ["read_only", "validated_profile"]
                if key == "write_support"
                else ["following_schedule", "manual_override", "off", "unknown"]
            )
        else:
            self._attr_name = DIAGNOSTICS[key]

    @property
    def native_value(self) -> int | str:
        system = self.coordinator.data.system
        if self._key == "mode_status":
            return {0: "following_schedule", 1: "manual_override", 8: "off"}.get(
                system.mode_raw, "unknown"
            )
        if self._key == "write_support":
            return "validated_profile" if system.write_supported else "read_only"
        if self._key == "raw_mode":
            return system.mode_raw
        if self._key == "raw_channel_count":
            return system.channel_count_raw
        raw = system.version_bytes if self._key == "raw_version_bytes" else system.controller_bytes
        return " ".join(f"{value:02X}" for value in raw)

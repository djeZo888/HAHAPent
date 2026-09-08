"""A constant version sensor; no timers, I/O, services, or device registry entry."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import INTEGRATION_VERSION


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Publish the version of this loaded code copy."""
    async_add_entities([HAHAPentTestVersionSensor()])


class HAHAPentTestVersionSensor(SensorEntity):
    """Report code version even while the Manager and developer computer are off."""

    _attr_name = "HAHAPent test installed version"
    _attr_unique_id = "hahapent_test_version"
    _attr_icon = "mdi:test-tube"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_native_value = INTEGRATION_VERSION

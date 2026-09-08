"""One stable native device independent of its editable network endpoint."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import AquariusCoordinator


class AquariusEntity(CoordinatorEntity[AquariusCoordinator]):
    """Base entity without restored state or a fabricated hardware identifier."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AquariusCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
        )

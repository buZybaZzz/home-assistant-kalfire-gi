"""Common device identity."""

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GiCoordinator


class GiEntity(CoordinatorEntity[GiCoordinator]):
    """An entity for one local fireplace."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GiCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.mac)},
            manufacturer="Kalfire",
            model="Gi",
            name="Kalfire Gi",
            sw_version=coordinator.firmware,
        )

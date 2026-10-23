"""Read-only Gi sensor entities."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GiConfigEntry
from .entity import GiEntity
from .gi.client import STATE_NAMES, Snapshot


@dataclass(frozen=True, kw_only=True)
class GiSensorDescription(SensorEntityDescription):
    value: Callable[[Snapshot], int | float | str]


SENSORS = (
    GiSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.temperature,
    ),
    GiSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATE_NAMES.values()),
        value=lambda data: STATE_NAMES[data.state],
    ),
    GiSensorDescription(
        key="error_code",
        translation_key="error_code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.error_code,
    ),
    GiSensorDescription(
        key="status_bits",
        translation_key="status_bits",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda data: data.status_bits,
    ),
    GiSensorDescription(
        key="flame_height",
        translation_key="flame_height",
        icon="mdi:fire",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.flame_height,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GiConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(GiSensor(entry.runtime_data, description) for description in SENSORS)


class GiSensor(GiEntity, SensorEntity):
    entity_description: GiSensorDescription

    def __init__(self, coordinator, description: GiSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | str:
        return self.entity_description.value(self.coordinator.data)

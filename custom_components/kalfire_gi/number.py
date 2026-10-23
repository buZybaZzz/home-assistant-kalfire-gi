"""Explicit normal flame and optional Spark settings; never restore values."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GiConfigEntry
from .const import CONF_CONTROL, CONF_SPARK
from .entity import GiEntity
from .gi.errors import KalfireError


async def async_setup_entry(
    hass: HomeAssistant, entry: GiConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.options.get(CONF_CONTROL, False):
        entities = [GiLevel(entry.runtime_data, "flame_height")]
        if entry.options.get(CONF_SPARK, False):
            entities.append(GiLevel(entry.runtime_data, "spark"))
        async_add_entities(entities)


class GiLevel(GiEntity, NumberEntity):
    """Display device readback, without optimistic acknowledgement or replay."""

    _attr_native_max_value = 5
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self.key = key
        self._attr_translation_key = key
        self._attr_native_min_value = 1 if key == "flame_height" else 0
        self._attr_icon = "mdi:fire" if key == "flame_height" else "mdi:creation"

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and data.state == 5
            and data.error_code == 0
            and getattr(data, self.key) is not None
            and self.native_min_value <= getattr(data, self.key) <= 5
        )

    @property
    def native_value(self) -> float | None:
        return getattr(self.coordinator.data, self.key)

    async def async_set_native_value(self, value: float) -> None:
        if isinstance(value, bool) or not self.native_min_value <= value <= 5 or value % 1:
            raise HomeAssistantError("Choose a whole level within the supported range")
        try:
            await self.coordinator.client.set_level(self.key, int(value))
        except KalfireError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            # Readback may lag; subsequent periodic polls remain read-only.
            await self.coordinator.async_request_refresh()

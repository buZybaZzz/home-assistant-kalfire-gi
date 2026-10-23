"""Explicit normal on/off actions; disabled until controls are opted into."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GiConfigEntry
from .const import CONF_CONTROL, CONF_EMBER
from .entity import GiEntity
from .gi.errors import KalfireError


async def async_setup_entry(
    hass: HomeAssistant, entry: GiConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    # No command entity exists until the user explicitly enables controls.
    if entry.options.get(CONF_CONTROL, False):
        entities = [GiSwitch(entry.runtime_data)]
        if entry.options.get(CONF_EMBER, False):
            entities.append(GiEmberFlicker(entry.runtime_data))
        async_add_entities(entities)


class GiSwitch(GiEntity, SwitchEntity):
    _attr_translation_key = "fireplace"
    _attr_icon = "mdi:fireplace"
    _attr_assumed_state = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fireplace")

    @property
    def is_on(self) -> bool:
        # These are requested-on states, including the normal startup sequence.
        return self.coordinator.data.state in (2, 3, 4, 5)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.start()
        except KalfireError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.stop()
        except KalfireError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()


class GiEmberFlicker(GiEntity, SwitchEntity):
    """The appliance's separate native LED shuffle mode, not a brightness effect."""

    _attr_translation_key = "ember_flicker"
    _attr_icon = "mdi:fire"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ember_flicker")

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and data.state in (0, 5)
            and data.error_code == 0
            and data.ember_status in range(7)
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.ember_status == 6

    async def _set_level(self, level: int) -> None:
        try:
            await self.coordinator.client.set_ember(level)
        except KalfireError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_level(6)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self._set_level(self.coordinator.last_ember_steady)

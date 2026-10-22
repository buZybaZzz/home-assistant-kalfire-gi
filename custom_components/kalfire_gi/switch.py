"""Explicit normal on/off actions; disabled until controls are opted into."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GiConfigEntry
from .const import CONF_CONTROL
from .entity import GiEntity
from .gi.errors import KalfireError


async def async_setup_entry(
    hass: HomeAssistant, entry: GiConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    # No command entity exists until the user explicitly enables controls.
    if entry.options.get(CONF_CONTROL, False):
        async_add_entities([GiSwitch(entry.runtime_data)])


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

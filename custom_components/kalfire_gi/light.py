"""Normal Ember Glow lighting, independently of gas ignition."""

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
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
    if entry.options.get(CONF_CONTROL, False) and entry.options.get(CONF_EMBER, False):
        async_add_entities([GiEmberGlow(entry.runtime_data)])


class GiEmberGlow(GiEntity, LightEntity):
    """Five steady levels and the appliance's native shuffle effect."""

    _attr_translation_key = "ember_glow"
    _attr_icon = "mdi:lightbulb"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = ["Steady", "Flicker"]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ember_glow")

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and data.state in (0, 5)
            and data.error_code == 0
            and data.ember_level is not None
            and data.ember_status is not None
        )

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data.ember_status)

    @property
    def brightness(self) -> int | None:
        level = self.coordinator.data.ember_status
        return round(level * 255 / 5) if level is not None and level < 6 else None

    @property
    def effect(self) -> str:
        return "Flicker" if self.coordinator.data.ember_status == 6 else "Steady"

    async def _set_level(self, level: int) -> None:
        try:
            await self.coordinator.client.set_ember(level)
        except KalfireError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        effect = kwargs.get(ATTR_EFFECT)
        if effect is not None and effect not in self.effect_list:
            raise HomeAssistantError("Unsupported Ember Glow effect")
        if effect == "Flicker":
            level = 6
        elif ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            if type(brightness) is not int or not 0 <= brightness <= 255:
                raise HomeAssistantError("Brightness must be between 0 and 255")
            level = max(1, min(5, round(brightness * 5 / 255))) if brightness else 0
        else:
            stored = self.coordinator.data.ember_level
            level = stored if stored in range(1, 7) else 3
            if effect == "Steady" and level == 6:
                level = 3
        await self._set_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_level(0)

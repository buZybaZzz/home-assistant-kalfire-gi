"""Kalfire Gi local CoAP/DTLS integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import CONF_FINGERPRINT, CONF_TOKEN, DOMAIN
from .coordinator import GiCoordinator
from .discovery import async_get_discovery
from .gi import GiClient
from .gi.errors import AuthenticationError, CannotConnect, KalfireError

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]
type GiConfigEntry = ConfigEntry[GiCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GiConfigEntry) -> bool:
    """Load by reading only; never restore or replay a previous on state."""
    client = GiClient(
        entry.data[CONF_HOST],
        entry.data[CONF_TOKEN],
        entry.data[CONF_FINGERPRINT],
        entry.data[CONF_PORT],
    )
    coordinator = None
    try:
        try:
            mac, firmware = await client.identity()
            if mac != entry.unique_id:
                raise CannotConnect("The configured address belongs to a different fireplace")
        except CannotConnect:
            client.close()
            connection = await async_get_discovery(hass).async_recover(entry)
            if connection is None:
                raise
            client = connection.client
            mac, firmware = entry.unique_id, connection.firmware
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_HOST: connection.host}
            )
        coordinator = GiCoordinator(hass, entry, client, mac, firmware)
        await coordinator.async_config_entry_first_refresh()
    except AuthenticationError as err:
        (coordinator.client if coordinator is not None else client).close()
        raise ConfigEntryAuthFailed("Local device pairing required") from err
    except KalfireError as err:
        (coordinator.client if coordinator is not None else client).close()
        raise ConfigEntryNotReady(str(err)) from err
    except BaseException:
        (coordinator.client if coordinator is not None else client).close()
        raise
    # Replace the former percentage light with discrete LED controls.
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity.domain == "light"
            and entity.platform == DOMAIN
            and entity.unique_id == f"{mac}_ember_glow"
        ):
            registry.async_remove(entity.entity_id)
    entry.runtime_data = coordinator
    # Recovery can replace the client while the same entities stay loaded.
    entry.async_on_unload(lambda: coordinator.client.close())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GiConfigEntry) -> None:
    if dict(entry.options) != entry.runtime_data.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

"""Kalfire Gi local CoAP/DTLS integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_FINGERPRINT, CONF_TOKEN
from .coordinator import GiCoordinator
from .gi import GiClient
from .gi.errors import AuthenticationError, KalfireError

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
    try:
        mac, firmware = await client.identity()
        if mac != entry.unique_id:
            raise ConfigEntryNotReady("The configured address belongs to a different fireplace")
        coordinator = GiCoordinator(hass, entry, client, mac, firmware)
        await coordinator.async_config_entry_first_refresh()
    except AuthenticationError as err:
        client.close()
        raise ConfigEntryAuthFailed("Local device pairing required") from err
    except KalfireError as err:
        client.close()
        raise ConfigEntryNotReady(str(err)) from err
    except BaseException:
        client.close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(client.close)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

"""Read-only periodic updates; actions are never part of a refresh."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL, CONF_SPARK, DEFAULT_POLL, DOMAIN
from .discovery import async_get_discovery
from .gi import GiClient, Snapshot
from .gi.errors import AuthenticationError, CannotConnect, KalfireError

_LOGGER = logging.getLogger(__name__)


class GiCoordinator(DataUpdateCoordinator[Snapshot]):
    """One polling subscription for all entities of a fireplace."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: GiClient, mac: str, firmware: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get(CONF_POLL, DEFAULT_POLL)),
        )
        self.last_ember_steady = 3
        self.options = dict(entry.options)
        self.include_ember = True
        self.include_spark = entry.options.get(CONF_SPARK, False)
        self.client = client
        self.mac = mac
        self.firmware = firmware

    async def _async_update_data(self) -> Snapshot:
        try:
            try:
                data = await self.client.snapshot(
                    include_spark=self.include_spark, include_ember=self.include_ember
                )
            except CannotConnect:
                assert self.config_entry is not None
                connection = await async_get_discovery(self.hass).async_recover(self.config_entry)
                if connection is None:
                    raise
                self.client.close()
                self.client = connection.client
                self.firmware = connection.firmware
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_HOST: connection.host},
                )
                data = await self.client.snapshot(
                    include_spark=self.include_spark, include_ember=self.include_ember
                )
            if data.ember_status in range(1, 6):
                self.last_ember_steady = data.ember_status
            return data
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("Local pairing is no longer valid") from err
        except KalfireError as err:
            raise UpdateFailed(str(err)) from err

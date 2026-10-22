"""Diagnostics deliberately exclude tokens, addresses, pins and serials."""

from dataclasses import asdict

from homeassistant.core import HomeAssistant

from . import GiConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: GiConfigEntry) -> dict:
    coordinator = entry.runtime_data
    return {
        "firmware": coordinator.firmware,
        "last_update_success": coordinator.last_update_success,
        "snapshot": asdict(coordinator.data) if coordinator.data else None,
    }

"""User-confirmed certificate trust and physical local pairing."""

import secrets
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_CONTROL,
    CONF_FINGERPRINT,
    CONF_POLL,
    CONF_SPARK,
    CONF_TOKEN,
    DEFAULT_POLL,
    DEFAULT_PORT,
    DOMAIN,
)
from .discovery import async_connect_candidate
from .gi import GiClient
from .gi.client import validate_token
from .gi.errors import AuthenticationError, CertificateChanged, KalfireError
from .gi.transport import DtlsTransport


class GiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Pair with a new token, or import an existing local token privately."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection: dict[str, Any] = {}
        self._new_token = secrets.token_hex(12)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GiOptionsFlow()

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        """Update a known fireplace only after pin and device identity checks."""
        mac = format_mac(discovery_info.macaddress)
        await self.async_set_unique_id(mac)
        entry = next(
            (item for item in self._async_current_entries() if item.unique_id == mac), None
        )
        if entry is None or entry.disabled_by is not None:
            return self.async_abort(reason="already_configured")
        if entry.data[CONF_HOST] == discovery_info.ip:
            return self.async_abort(reason="already_configured")
        original_data = dict(entry.data)
        connection = await async_connect_candidate(entry, discovery_info.ip)
        if connection is not None:
            connection.client.close()
            if dict(entry.data) == original_data:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_HOST: discovery_info.ip}
                )
                if entry.state in (
                    config_entries.ConfigEntryState.LOADED,
                    config_entries.ConfigEntryState.SETUP_RETRY,
                ):
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_abort(reason="already_configured")

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if not host or "://" in host or "/" in host:
                errors[CONF_HOST] = "invalid_host"
            else:
                self._connection = {CONF_HOST: host, CONF_PORT: user_input[CONF_PORT]}
                probe = DtlsTransport(host, user_input[CONF_PORT])
                try:
                    self._connection[CONF_FINGERPRINT] = await probe.connect()
                except KalfireError:
                    errors["base"] = "cannot_connect"
                finally:
                    probe.close()
                if not errors:
                    return await self.async_step_trust()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_trust(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return await self.async_step_auth_method()
        return self.async_show_form(
            step_id="trust",
            data_schema=vol.Schema({}),
            description_placeholders={
                "host": self._connection[CONF_HOST],
                "fingerprint": self._connection[CONF_FINGERPRINT],
            },
        )

    async def async_step_auth_method(self, user_input=None):
        return self.async_show_menu(step_id="auth_method", menu_options=["pair", "existing_token"])

    async def _complete(self, token: str):
        client = GiClient(
            self._connection[CONF_HOST],
            token,
            self._connection[CONF_FINGERPRINT],
            self._connection[CONF_PORT],
        )
        try:
            # Same initial read as the official Gi pairing flow; no ignition command.
            await client.read("sys.info.bsn")
            mac, _firmware = await client.identity()
        finally:
            client.close()
        data = {**self._connection, CONF_TOKEN: token}
        if self.source == config_entries.SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if mac != entry.unique_id:
                return self.async_abort(reason="wrong_device")
            return self.async_update_reload_and_abort(entry, data_updates=data)
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Kalfire Gi", data=data)

    async def async_step_pair(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            try:
                return await self._complete(self._new_token)
            except AuthenticationError:
                errors["base"] = "pairing_failed"
            except CertificateChanged:
                errors["base"] = "certificate_changed"
            except KalfireError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="pair", data_schema=vol.Schema({}), errors=errors)

    async def async_step_existing_token(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            try:
                token = validate_token(user_input[CONF_TOKEN].strip())
                return await self._complete(token)
            except ValueError:
                errors[CONF_TOKEN] = "invalid_token"
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CertificateChanged:
                errors["base"] = "certificate_changed"
            except KalfireError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="existing_token",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        self._connection = {
            key: entry_data[key] for key in (CONF_HOST, CONF_PORT, CONF_FINGERPRINT)
        }
        return await self.async_step_auth_method()

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            self._connection = {**entry.data, **user_input}
            try:
                client = GiClient(
                    self._connection[CONF_HOST],
                    self._connection[CONF_TOKEN],
                    self._connection[CONF_FINGERPRINT],
                    self._connection[CONF_PORT],
                )
                try:
                    mac, _firmware = await client.identity()
                finally:
                    client.close()
                if mac != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            except CertificateChanged:
                errors["base"] = "certificate_changed"
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except KalfireError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                }
            ),
            errors=errors,
        )


class GiOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONTROL, default=self.config_entry.options.get(CONF_CONTROL, False)
                    ): bool,
                    vol.Required(
                        CONF_SPARK, default=self.config_entry.options.get(CONF_SPARK, False)
                    ): bool,
                    vol.Required(
                        CONF_POLL, default=self.config_entry.options.get(CONF_POLL, DEFAULT_POLL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=300)),
                }
            ),
        )

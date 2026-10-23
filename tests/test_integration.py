"""Exercise real Home Assistant setup, config flows, entities and reloads."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kalfire_gi.const import CONF_CONTROL, DOMAIN
from custom_components.kalfire_gi.gi import Snapshot
from custom_components.kalfire_gi.gi.errors import (
    AuthenticationError,
    CannotConnect,
    CertificateChanged,
)

DATA = {CONF_HOST: "fireplace.invalid", CONF_PORT: 5684, "token": "a" * 24, "fingerprint": "b" * 64}
MAC = "02:00:00:00:00:01"


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.identity = AsyncMock(return_value=(MAC, "0.7.11"))
    client.read = AsyncMock(return_value="example-serial")
    client.snapshot = AsyncMock(return_value=Snapshot(20.7, 5, 0, 2415, 0))
    client.start = AsyncMock()
    client.stop = AsyncMock()
    return client


async def test_setup_sensors_no_commands_and_reload(hass, fake_client):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        states = list(hass.states.async_all())
        assert any(s.state == "20.7" for s in states)
        assert any(s.state == "running" for s in states)
        assert not any(s.domain == "switch" for s in states)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        fake_client.start.assert_not_awaited()
        fake_client.stop.assert_not_awaited()
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        fake_client.close.assert_called()


async def test_controls_only_on_explicit_service_call(hass, fake_client):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA, options={CONF_CONTROL: True})
    entry.add_to_hass(hass)
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        switch = next(s for s in hass.states.async_all() if s.domain == "switch")
        fake_client.start.assert_not_awaited()
        fake_client.stop.assert_not_awaited()
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True
        )
        fake_client.start.assert_awaited_once()
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": switch.entity_id}, blocking=True
        )
        fake_client.stop.assert_awaited_once()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_changed_certificate_prevents_setup(hass, fake_client):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    fake_client.identity.side_effect = CertificateChanged("changed")
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    fake_client.snapshot.assert_not_awaited()
    fake_client.start.assert_not_awaited()
    fake_client.close.assert_called_once()


async def _begin_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    probe = MagicMock(connect=AsyncMock(return_value=DATA["fingerprint"]))
    with patch("custom_components.kalfire_gi.config_flow.DtlsTransport", return_value=probe):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: DATA[CONF_HOST], CONF_PORT: 5684}
        )
    assert result["step_id"] == "trust"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    return result


async def test_token_flow_and_duplicate(hass, fake_client):
    result = await _begin_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "existing_token"}
    )
    with (
        patch("custom_components.kalfire_gi.config_flow.GiClient", return_value=fake_client),
        patch("custom_components.kalfire_gi.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": DATA["token"]}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == DATA
        assert result["result"].unique_id == MAC
        await hass.async_block_till_done()
        second = await _begin_flow(hass)
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"], {"next_step_id": "existing_token"}
        )
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"], {"token": DATA["token"]}
        )
        assert second["reason"] == "already_configured"
    fake_client.start.assert_not_awaited()
    fake_client.stop.assert_not_awaited()


async def test_physical_pairing_failure_can_retry(hass, fake_client):
    result = await _begin_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pair"}
    )
    fake_client.read.side_effect = AuthenticationError("not paired")
    with patch("custom_components.kalfire_gi.config_flow.GiClient", return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": "pairing_failed"}
    fake_client.close.assert_called()


async def test_unreachable_in_user_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    probe = MagicMock(connect=AsyncMock(side_effect=CannotConnect("offline")))
    with patch("custom_components.kalfire_gi.config_flow.DtlsTransport", return_value=probe):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "fireplace.invalid", CONF_PORT: 5684}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    probe.close.assert_called_once()


async def test_optional_levels_readback_and_unavailability(hass, fake_client):
    from custom_components.kalfire_gi.const import CONF_SPARK

    fake_client.snapshot.return_value = Snapshot(20.7, 5, 0, 2415, 3, spark=0)
    fake_client.set_level = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=MAC, data=DATA, options={CONF_CONTROL: True, CONF_SPARK: True}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        levels = {
            s.attributes["friendly_name"]: s
            for s in hass.states.async_all()
            if s.domain == "number"
        }
        assert len(levels) == 2
        spark = next(s for s in levels.values() if s.attributes["min"] == 0)
        fake_client.set_level.assert_not_awaited()
        await hass.services.async_call(
            "number", "set_value", {"entity_id": spark.entity_id, "value": 5}, blocking=True
        )
        fake_client.set_level.assert_awaited_once_with("spark", 5)
        assert hass.states.get(spark.entity_id).state == "0"  # ACK is not readback.
        fake_client.snapshot.return_value = Snapshot(20.7, 5, 0, 2415, 3, spark=5)
        await entry.runtime_data.async_refresh()
        assert hass.states.get(spark.entity_id).state == "5"
        fake_client.snapshot.side_effect = CannotConnect("offline")
        await entry.runtime_data.async_refresh()
        assert hass.states.get(spark.entity_id).state == "unavailable"
        fake_client.snapshot.side_effect = None
        fake_client.snapshot.return_value = Snapshot(20.7, 0, 0, 2415, 3, spark=5)
        await entry.runtime_data.async_refresh()
        assert hass.states.get(spark.entity_id).state == "unavailable"
        fake_client.set_level.assert_awaited_once()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_ember_light_works_with_gas_off_without_ignition(hass, fake_client):
    from custom_components.kalfire_gi.const import CONF_EMBER

    fake_client.snapshot.return_value = Snapshot(20.7, 0, 0, 2400, 1, ember_level=1, ember_status=0)
    fake_client.set_ember = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=MAC, data=DATA, options={CONF_CONTROL: True, CONF_EMBER: True}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        light = next(s for s in hass.states.async_all() if s.domain == "light")
        assert light.state == "off"
        fake_client.set_ember.assert_not_awaited()
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light.entity_id, "brightness": 153}, blocking=True
        )
        fake_client.set_ember.assert_awaited_once_with(3)
        assert hass.states.get(light.entity_id).state == "off"  # Never optimistic.
        fake_client.snapshot.return_value = Snapshot(
            20.7, 0, 0, 2400, 1, ember_level=6, ember_status=6
        )
        await entry.runtime_data.async_refresh()
        assert hass.states.get(light.entity_id).state == "on"
        assert hass.states.get(light.entity_id).attributes["effect"] == "Flicker"
        await hass.services.async_call(
            "light", "turn_off", {"entity_id": light.entity_id}, blocking=True
        )
        assert fake_client.set_ember.await_args.args == (0,)
        fake_client.start.assert_not_awaited()
        fake_client.stop.assert_not_awaited()
        await hass.config_entries.async_unload(entry.entry_id)

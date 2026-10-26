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
        assert not any(s.entity_id.endswith("_fireplace") for s in states)
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
        switch = next(
            s
            for s in hass.states.async_all()
            if s.domain == "switch" and s.entity_id.endswith("_fireplace")
        )
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
        assert len(levels) == 3
        spark = next(s for s in levels.values() if "Sparks" in s.attributes["friendly_name"])
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


@pytest.mark.parametrize(
    "options",
    [
        {},
        {CONF_CONTROL: False, "enable_ember_glow": False},
        {CONF_CONTROL: True, "enable_ember_glow": True},
    ],
)
async def test_ember_discrete_controls_and_light_migration(hass, fake_client, options):
    from homeassistant.helpers import entity_registry as er

    from custom_components.kalfire_gi.const import CONF_SPARK

    fake_client.snapshot.return_value = Snapshot(
        20.7, 0, 0, 2400, 1, spark=0, ember_level=1, ember_status=0
    )
    fake_client.set_ember = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data=DATA,
        options={**options, CONF_SPARK: True},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    legacy = registry.async_get_or_create("light", DOMAIN, f"{MAC}_ember_glow", config_entry=entry)
    unrelated = registry.async_get_or_create("light", DOMAIN, "unrelated", config_entry=entry)
    with patch("custom_components.kalfire_gi.GiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert registry.async_get(legacy.entity_id) is None
        assert registry.async_get(unrelated.entity_id) is not None
        assert not any(s.domain == "light" for s in hass.states.async_all())
        ember = next(
            s
            for s in hass.states.async_all()
            if s.domain == "number" and "Ember Glow" in s.attributes["friendly_name"]
        )
        flicker = next(
            s
            for s in hass.states.async_all()
            if s.domain == "switch" and "Flicker" in s.attributes["friendly_name"]
        )
        assert ember.state == "0"
        assert (
            ember.attributes["min"] == 0
            and ember.attributes["max"] == 5
            and ember.attributes["step"] == 1
        )
        assert any(
            "Sparks" in s.attributes.get("friendly_name", "") for s in hass.states.async_all()
        ) == options.get(CONF_CONTROL, False)
        fake_client.snapshot.assert_awaited_with(include_spark=True, include_ember=True)
        fake_client.set_ember.assert_not_awaited()
        await hass.services.async_call(
            "number", "set_value", {"entity_id": ember.entity_id, "value": 2}, blocking=True
        )
        fake_client.set_ember.assert_awaited_once_with(2)
        assert hass.states.get(ember.entity_id).state == "0"
        fake_client.snapshot.return_value = Snapshot(
            20.7, 0, 0, 2400, 1, ember_level=2, ember_status=2
        )
        await entry.runtime_data.async_refresh()
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": flicker.entity_id}, blocking=True
        )
        assert fake_client.set_ember.await_args.args == (6,)
        fake_client.snapshot.return_value = Snapshot(
            20.7, 0, 0, 2400, 1, ember_level=6, ember_status=6
        )
        await entry.runtime_data.async_refresh()
        assert hass.states.get(flicker.entity_id).state == "on"
        assert hass.states.get(ember.entity_id).state == "unavailable"
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": flicker.entity_id}, blocking=True
        )
        assert fake_client.set_ember.await_args.args == (2,)
        fake_client.start.assert_not_awaited()
        fake_client.stop.assert_not_awaited()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_options_no_longer_offer_ember_toggle(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data=DATA,
        options={CONF_CONTROL: False, "enable_ember_glow": False},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "enable_ember_glow" not in {key.schema for key in result["data_schema"].schema}
    with patch("custom_components.kalfire_gi._async_options_updated", return_value=None):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_CONTROL: False, "enable_spark": False, "poll_interval": 30},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "enable_ember_glow" not in entry.options


@pytest.mark.parametrize("hosts", [(), ("192.0.2.22",), ("192.0.2.22", "192.0.2.23")])
async def test_initial_discovery_prefills_and_keeps_manual_entry(hass, hosts):
    from custom_components.kalfire_gi.discovery import GiDiscovery

    with patch.object(GiDiscovery, "async_candidates", return_value=hosts) as scan:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    scan.assert_awaited_once()
    assert result["step_id"] == "user"
    schema = result["data_schema"]
    if hosts:
        assert schema({CONF_PORT: 5684})[CONF_HOST] == hosts[0]
    if len(hosts) > 1:
        host_selector = next(value for key, value in schema.schema.items() if key == CONF_HOST)
        assert host_selector.config["options"] == list(hosts)
        assert host_selector.config["custom_value"] is True
        assert schema({CONF_HOST: hosts[1], CONF_PORT: 5684})[CONF_HOST] == hosts[1]
    probe = MagicMock(connect=AsyncMock(return_value=DATA["fingerprint"]))
    with patch("custom_components.kalfire_gi.config_flow.DtlsTransport", return_value=probe):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "manual.invalid", CONF_PORT: 1234}
        )
    assert result["step_id"] == "trust"
    assert result["description_placeholders"]["host"] == "manual.invalid"
    probe.connect.assert_awaited_once()
    probe.close.assert_called_once()


async def test_discovered_address_requires_trust_and_preserves_failed_input(hass):
    from custom_components.kalfire_gi.discovery import GiDiscovery

    with patch.object(GiDiscovery, "async_candidates", return_value=("192.0.2.22",)) as scan:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        probe = MagicMock(connect=AsyncMock(side_effect=CannotConnect("offline")))
        with patch("custom_components.kalfire_gi.config_flow.DtlsTransport", return_value=probe):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: "192.0.2.22", CONF_PORT: 1234}
            )
            assert result["errors"] == {"base": "cannot_connect"}
            assert result["data_schema"]({}) == {CONF_HOST: "192.0.2.22", CONF_PORT: 1234}
            probe.connect.side_effect = None
            probe.connect.return_value = DATA["fingerprint"]
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: "192.0.2.22", CONF_PORT: 1234}
            )
        scan.assert_awaited_once()
    assert result["step_id"] == "trust"
    assert result["description_placeholders"] == {
        "host": "192.0.2.22",
        "fingerprint": DATA["fingerprint"],
    }

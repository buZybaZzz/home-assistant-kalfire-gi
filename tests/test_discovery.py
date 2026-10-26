"""Address recovery with real HA lifecycle and fake discovery/DTLS peers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kalfire_gi.const import DOMAIN
from custom_components.kalfire_gi.discovery import (
    DISCOVERY_GROUP,
    DISCOVERY_PORT,
    DISCOVERY_QUERY,
    GiDiscovery,
    _async_scan_interface,
    async_connect_candidate,
    async_get_discovery,
)
from custom_components.kalfire_gi.gi import Snapshot
from custom_components.kalfire_gi.gi.errors import (
    AuthenticationError,
    CannotConnect,
    CertificateChanged,
)

MAC = "02:00:00:00:00:01"
HOST = "192.0.2.22"
NEW_HOST = "192.0.2.23"
DATA = {CONF_HOST: HOST, CONF_PORT: 5684, "token": "a" * 24, "fingerprint": "b" * 64}


def make_client(mac=MAC):
    return MagicMock(
        identity=AsyncMock(return_value=(mac, "0.7.11")),
        snapshot=AsyncMock(return_value=Snapshot(20.7, 0, 0, 2400, 3)),
        start=AsyncMock(),
        stop=AsyncMock(),
        set_level=AsyncMock(),
        set_ember=AsyncMock(),
    )


def assert_no_commands(*clients):
    for client in clients:
        for method in (client.start, client.stop, client.set_level, client.set_ember):
            method.assert_not_awaited()


async def test_startup_finds_changed_address_and_preserves_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    old, new = make_client(), make_client()
    old.identity.side_effect = CannotConnect("offline")
    with (
        patch("custom_components.kalfire_gi.GiClient", return_value=old),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=new) as factory,
        patch.object(GiDiscovery, "async_candidates", return_value=(NEW_HOST,)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.data == {**DATA, CONF_HOST: NEW_HOST}
        assert entry.unique_id == MAC
        assert entry.runtime_data.client is new
        factory.assert_called_once_with(NEW_HOST, DATA["token"], DATA["fingerprint"], 5684)
        assert_no_commands(old, new)
        await hass.config_entries.async_unload(entry.entry_id)
        new.close.assert_called_once()


async def test_poll_recovers_without_replacing_entities_or_device(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    old, new = make_client(), make_client()
    with (
        patch("custom_components.kalfire_gi.GiClient", return_value=old),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=new),
        patch.object(GiDiscovery, "async_candidates", return_value=(NEW_HOST,)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        registry = er.async_get(hass)
        entities = {
            item.entity_id: item.id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        device_id = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0].id
        old.snapshot.side_effect = CannotConnect("address moved")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert entry.runtime_data is coordinator
        assert coordinator.client is new
        assert coordinator.last_update_success
        assert entry.data == {**DATA, CONF_HOST: NEW_HOST}
        assert entities == {
            item.entity_id: item.id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert (
            device_id == dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0].id
        )
        assert_no_commands(old, new)
        await hass.config_entries.async_unload(entry.entry_id)
        new.close.assert_called_once()


@pytest.mark.parametrize("failure", [AuthenticationError("unpaired"), CertificateChanged("pin")])
async def test_security_errors_at_current_host_do_not_scan(hass, failure):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client()
    client.identity.side_effect = failure
    with (
        patch("custom_components.kalfire_gi.GiClient", return_value=client),
        patch.object(GiDiscovery, "async_candidates") as scan,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        scan.assert_not_awaited()
        assert entry.data == DATA
        assert_no_commands(client)


@pytest.mark.parametrize("result", ["wrong_mac", "bad_pin", "bad_token", "offline"])
async def test_untrusted_candidates_are_closed_and_never_saved(hass, result):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client("02:00:00:00:00:02")
    if result != "wrong_mac":
        client.identity.side_effect = {
            "bad_pin": CertificateChanged("pin"),
            "bad_token": AuthenticationError("token"),
            "offline": CannotConnect("offline"),
        }[result]
    with patch("custom_components.kalfire_gi.discovery.GiClient", return_value=client):
        assert await async_connect_candidate(entry, NEW_HOST) is None
    client.close.assert_called_once()
    assert entry.data == DATA
    assert_no_commands(client)


async def test_candidate_cancellation_closes_connection(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    client = make_client()
    client.identity.side_effect = asyncio.CancelledError
    with patch("custom_components.kalfire_gi.discovery.GiClient", return_value=client):
        with pytest.raises(asyncio.CancelledError):
            await async_connect_candidate(entry, NEW_HOST)
    client.close.assert_called_once()


async def test_shared_scan_cooldown_and_retry(hass):
    discovery = async_get_discovery(hass)
    with (
        patch.object(discovery, "_async_scan", return_value=(NEW_HOST,)) as scan,
        patch("custom_components.kalfire_gi.discovery.time.monotonic", return_value=100),
    ):
        assert await asyncio.gather(discovery.async_candidates(), discovery.async_candidates()) == [
            (NEW_HOST,),
            (NEW_HOST,),
        ]
        assert await discovery.async_candidates() == (NEW_HOST,)
        scan.assert_awaited_once()
    with (
        patch.object(discovery, "_async_scan", return_value=()) as scan,
        patch("custom_components.kalfire_gi.discovery.time.monotonic", return_value=161),
    ):
        assert await discovery.async_candidates() == ()
        scan.assert_awaited_once()


async def test_recovery_checks_multiple_peers_and_limits_repeated_attempts(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    other, own = make_client("02:00:00:00:00:02"), make_client()
    discovery = async_get_discovery(hass)
    with (
        patch.object(
            discovery, "async_candidates", return_value=(HOST, "192.0.2.24", NEW_HOST)
        ) as scan,
        patch("custom_components.kalfire_gi.discovery.GiClient", side_effect=[other, own]),
    ):
        connection = await discovery.async_recover(entry)
        assert connection.host == NEW_HOST
        assert await discovery.async_recover(entry) is None
        scan.assert_awaited_once()
        other.close.assert_called_once()
        own.close.assert_not_called()
        own.close()


@pytest.mark.parametrize("trusted", [True, False])
async def test_dhcp_updates_only_verified_existing_device(hass, trusted):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client(MAC if trusted else "02:00:00:00:00:02")
    with patch("custom_components.kalfire_gi.discovery.GiClient", return_value=client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip=NEW_HOST, hostname="unreliable-name", macaddress=MAC.replace(":", "")
            ),
        )
        await hass.async_block_till_done()
    assert result["reason"] == "already_configured"
    assert entry.data == {**DATA, CONF_HOST: NEW_HOST if trusted else HOST}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    client.close.assert_called_once()
    assert_no_commands(client)


async def test_disabled_entry_ignores_dhcp(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=MAC, data=DATA, disabled_by=config_entries.ConfigEntryDisabler.USER
    )
    entry.add_to_hass(hass)
    with patch("custom_components.kalfire_gi.discovery.GiClient") as factory:
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(ip=NEW_HOST, hostname="", macaddress=MAC.replace(":", "")),
        )
    factory.assert_not_called()
    assert entry.data == DATA


async def test_only_enabled_ipv4_interfaces_are_scanned(hass):
    discovery = async_get_discovery(hass)
    with (
        patch(
            "custom_components.kalfire_gi.discovery.network.async_get_adapters",
            return_value=[
                {"enabled": True, "ipv4": [{"address": HOST}, {"address": "127.0.0.1"}]},
                {"enabled": False, "ipv4": [{"address": "192.0.2.90"}]},
            ],
        ),
        patch(
            "custom_components.kalfire_gi.discovery._async_scan_interface", return_value=(NEW_HOST,)
        ) as scan,
    ):
        assert await discovery.async_candidates() == (NEW_HOST,)
        scan.assert_awaited_once_with(HOST)


async def test_discovery_cancellation_does_not_cancel_shared_scan(hass):
    discovery = async_get_discovery(hass)
    started, finish = asyncio.Event(), asyncio.Event()

    async def scan():
        started.set()
        await finish.wait()
        return (NEW_HOST,)

    with patch.object(discovery, "_async_scan", side_effect=scan):
        waiter = asyncio.create_task(discovery.async_candidates())
        await started.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not discovery._scan_task.cancelled()
        finish.set()
        assert await discovery.async_candidates() == (NEW_HOST,)


async def test_stop_cancels_inflight_scan(hass):
    discovery = async_get_discovery(hass)
    started = asyncio.Event()

    async def scan():
        started.set()
        await asyncio.Event().wait()

    with patch.object(discovery, "_async_scan", side_effect=scan):
        waiter = asyncio.create_task(discovery.async_candidates())
        await started.wait()
        await discovery.async_stop(None)
        with pytest.raises(asyncio.CancelledError):
            await waiter


async def test_wire_query_filters_replies_and_closes_socket(hass):
    # Use the real datagram implementation despite the default offline scan fixture.
    import custom_components.kalfire_gi.discovery as module

    sock = MagicMock()
    sock.__enter__.return_value = sock
    loop = asyncio.get_running_loop()
    with (
        patch.object(module.socket, "socket", return_value=sock),
        patch.object(loop, "sock_sendto", new_callable=AsyncMock) as send,
        patch.object(
            loop,
            "sock_recvfrom",
            new_callable=AsyncMock,
            side_effect=[
                (b"Kalfire GI", (NEW_HOST, 9999)),
                (b"other device", ("192.0.2.24", 3333)),
                (b"Kalfire GI", (NEW_HOST, 3333)),
                TimeoutError(),
            ],
        ),
    ):
        assert await _async_scan_interface(HOST) == (NEW_HOST,)
        send.assert_awaited_once_with(sock, DISCOVERY_QUERY, (DISCOVERY_GROUP, DISCOVERY_PORT))
        sock.bind.assert_called_once_with((HOST, 0))
        sock.__exit__.assert_called_once()


async def test_dhcp_reload_preserves_entities_and_does_not_replay_commands(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    old, new = make_client(), make_client()
    with (
        patch("custom_components.kalfire_gi.GiClient", side_effect=[old, new]),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=new),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        registry = er.async_get(hass)
        entities = {
            item.entity_id: item.id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(ip=NEW_HOST, hostname="", macaddress=MAC.replace(":", "")),
        )
        await hass.async_block_till_done()
        assert result["reason"] == "already_configured"
        assert entry.runtime_data is not coordinator
        assert entry.runtime_data.client is new
        assert entry.data == {**DATA, CONF_HOST: NEW_HOST}
        assert entities == {
            item.entity_id: item.id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert_no_commands(old, new)
        await hass.config_entries.async_unload(entry.entry_id)


async def test_no_discovery_reply_leaves_entry_unavailable_and_retries_are_bounded(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client()
    with (
        patch("custom_components.kalfire_gi.GiClient", return_value=client),
        patch.object(GiDiscovery, "async_candidates", return_value=()) as scan,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        client.snapshot.side_effect = CannotConnect("offline")
        await entry.runtime_data.async_refresh()
        await entry.runtime_data.async_refresh()
        scan.assert_awaited_once()
        assert not entry.runtime_data.last_update_success
        assert entry.data == DATA
        assert_no_commands(client)
        await hass.config_entries.async_unload(entry.entry_id)


async def test_recovery_deadline_closes_candidate_and_leaves_address_unchanged(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client()

    async def wait_for_peer():
        await asyncio.Event().wait()

    client.identity.side_effect = wait_for_peer
    with (
        patch.object(GiDiscovery, "async_candidates", return_value=(NEW_HOST,)),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=client),
        patch("custom_components.kalfire_gi.discovery.RECOVERY_SECONDS", 0.01),
    ):
        assert await async_get_discovery(hass).async_recover(entry) is None
    client.close.assert_called_once()
    assert entry.data == DATA


async def test_recovery_does_not_overwrite_concurrent_reconfiguration(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    client = make_client()

    async def changed_configuration():
        hass.config_entries.async_update_entry(entry, data={**DATA, CONF_HOST: "192.0.2.99"})
        return MAC, "0.7.11"

    client.identity.side_effect = changed_configuration
    with (
        patch.object(GiDiscovery, "async_candidates", return_value=(NEW_HOST,)),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=client),
    ):
        assert await async_get_discovery(hass).async_recover(entry) is None
    assert entry.data[CONF_HOST] == "192.0.2.99"
    client.close.assert_called_once()


async def test_failed_first_refresh_closes_replacement_client(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data=DATA)
    entry.add_to_hass(hass)
    old, new = make_client(), make_client()
    old.snapshot.side_effect = CannotConnect("moved during setup")
    new.snapshot.side_effect = AuthenticationError("pairing lost")
    with (
        patch("custom_components.kalfire_gi.GiClient", return_value=old),
        patch("custom_components.kalfire_gi.discovery.GiClient", return_value=new),
        patch.object(GiDiscovery, "async_candidates", return_value=(NEW_HOST,)),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    new.close.assert_called_once()
    assert_no_commands(old, new)


@pytest.mark.parametrize(
    ("host", "addresses", "expected"),
    [
        ("192.168.10.50", [("192.168.10.2", 24)], True),
        ("192.168.20.50", [("192.168.10.2", 24)], False),
        ("192.168.20.50", [("192.168.10.2", 16)], True),
        ("192.168.20.50", [("192.168.10.2", 24), ("192.168.20.2", 24)], True),
        ("192.168.20.50", [("127.0.0.1", 8)], None),
        ("192.168.20.50", [], None),
        ("fireplace.local", [("192.168.10.2", 24)], None),
        ("2001:db8::1", [("192.168.10.2", 24)], None),
    ],
)
async def test_subnet_comparison_uses_actual_prefixes(hass, host, addresses, expected):
    from custom_components.kalfire_gi.discovery import async_same_subnet

    with patch(
        "custom_components.kalfire_gi.discovery.network.async_get_adapters",
        return_value=[
            {
                "enabled": True,
                "ipv4": [{"address": ip, "network_prefix": prefix} for ip, prefix in addresses],
            },
            {"enabled": False, "ipv4": [{"address": "192.168.20.2", "network_prefix": 24}]},
        ],
    ):
        assert await async_same_subnet(hass, host) is expected


async def test_subnet_unavailable_adapters_are_unknown(hass):
    from custom_components.kalfire_gi.discovery import async_same_subnet

    with patch(
        "custom_components.kalfire_gi.discovery.network.async_get_adapters",
        side_effect=OSError,
    ):
        assert await async_same_subnet(hass, HOST) is None

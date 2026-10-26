"""Bounded local discovery; an address is trusted only after pinned identity reads."""

import asyncio
import contextlib
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass

from homeassistant.components import network
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant

from .const import CONF_FINGERPRINT, CONF_TOKEN, DOMAIN
from .gi import GiClient
from .gi.errors import KalfireError

_LOGGER = logging.getLogger(__name__)
DISCOVERY_GROUP = "239.10.11.13"
DISCOVERY_PORT = 3333
DISCOVERY_QUERY = b"WHEREIS lanboard"
DISCOVERY_REPLY = b"Kalfire GI"
SCAN_SECONDS = 5
RECOVERY_SECONDS = 25
RETRY_SECONDS = 60
MAX_CANDIDATES = 8
MAX_DATAGRAMS = 64


def _is_address(host: str) -> bool:
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return False
    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address.is_link_local
        or address == ipaddress.IPv4Address("255.255.255.255")
    )


@dataclass
class DiscoveredConnection:
    """A live client whose pin and MAC have both been checked."""

    client: GiClient
    host: str
    firmware: str


async def async_connect_candidate(entry: ConfigEntry, host: str) -> DiscoveredConnection | None:
    """Read identity through the existing pin and token, never pair or control."""
    if not _is_address(host) or not entry.unique_id:
        return None
    client = GiClient(
        host, entry.data[CONF_TOKEN], entry.data[CONF_FINGERPRINT], entry.data[CONF_PORT]
    )
    try:
        mac, firmware = await client.identity()
        if mac == entry.unique_id:
            return DiscoveredConnection(client, host, firmware)
    except KalfireError:
        pass
    except BaseException:
        client.close()
        raise
    client.close()
    return None


async def _async_scan_interface(address: str) -> tuple[str, ...]:
    """One discovery datagram per interface, with unicast replies to our socket."""
    loop = asyncio.get_running_loop()
    hosts: dict[str, None] = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setblocking(False)
            sock.bind((address, 0))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            async with asyncio.timeout(SCAN_SECONDS):
                await loop.sock_sendto(sock, DISCOVERY_QUERY, (DISCOVERY_GROUP, DISCOVERY_PORT))
                for _ in range(MAX_DATAGRAMS):
                    payload, peer = await loop.sock_recvfrom(sock, 256)
                    if (
                        payload == DISCOVERY_REPLY
                        and peer[1] == DISCOVERY_PORT
                        and _is_address(peer[0])
                    ):
                        hosts[peer[0]] = None
                        if len(hosts) >= MAX_CANDIDATES:
                            break
    except TimeoutError:
        pass
    except OSError:
        _LOGGER.debug("Local fireplace discovery is unavailable on a network interface")
    return tuple(hosts)


class GiDiscovery:
    """Share scans across entries and bound repeated recovery attempts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._scan_task: asyncio.Task[tuple[str, ...]] | None = None
        self._last_scan = float("-inf")
        self._next_attempt: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._verification_slots = asyncio.Semaphore(2)

    async def async_stop(self, _event: Event) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task

    async def _async_scan(self) -> tuple[str, ...]:
        addresses = {
            ip["address"]
            for adapter in await network.async_get_adapters(self.hass)
            if adapter["enabled"]
            for ip in adapter["ipv4"]
            if _is_address(ip["address"])
        }
        results = await asyncio.gather(*(_async_scan_interface(ip) for ip in addresses))
        return tuple(dict.fromkeys(host for result in results for host in result))[:MAX_CANDIDATES]

    async def async_candidates(self) -> tuple[str, ...]:
        if self._scan_task is None or (
            self._scan_task.done() and time.monotonic() - self._last_scan >= RETRY_SECONDS
        ):
            self._last_scan = time.monotonic()
            self._scan_task = self.hass.async_create_background_task(
                self._async_scan(), "Kalfire Gi discovery"
            )
        # Unloading one entry must not cancel the shared scan of another entry.
        return await asyncio.shield(self._scan_task)

    async def async_recover(self, entry: ConfigEntry) -> DiscoveredConnection | None:
        async with self._locks.setdefault(entry.entry_id, asyncio.Lock()):
            if time.monotonic() < self._next_attempt.get(entry.entry_id, 0):
                return None
            self._next_attempt[entry.entry_id] = time.monotonic() + RETRY_SECONDS
            original_data = dict(entry.data)
            try:
                async with asyncio.timeout(RECOVERY_SECONDS):
                    # DHCP events use the config flow; this fallback needs no DHCP traffic.
                    hosts = await self.async_candidates()
                    for host in tuple(dict.fromkeys(hosts))[:MAX_CANDIDATES]:
                        if host == original_data[CONF_HOST]:
                            continue
                        async with self._verification_slots:
                            connection = await async_connect_candidate(entry, host)
                        if connection is not None:
                            if dict(entry.data) != original_data:
                                connection.client.close()
                                return None
                            return connection
            except TimeoutError:
                pass
            return None


def async_get_discovery(hass: HomeAssistant) -> GiDiscovery:
    """Return the shared discovery service without starting a periodic scanner."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = discovery = GiDiscovery(hass)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, discovery.async_stop)
    return hass.data[DOMAIN]

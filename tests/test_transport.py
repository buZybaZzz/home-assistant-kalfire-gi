"""Trust boundary: no credentials before acceptance; changed pins fail closed."""

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kalfire_gi.gi.errors import CertificateChanged, ProtocolError
from custom_components.kalfire_gi.gi.transport import DtlsTransport


async def test_untrusted_probe_cannot_send_token():
    transport = DtlsTransport("fireplace.invalid")
    transport._ssl = MagicMock()
    transport._drive = AsyncMock()
    with pytest.raises(ProtocolError):
        await transport.send(b"token=secret")
    transport._drive.assert_not_awaited()


async def test_changed_certificate_blocks_application_data():
    transport = DtlsTransport("fireplace.invalid", fingerprint="0" * 64)
    transport._drive = AsyncMock()
    fake_socket = MagicMock()
    fake_ssl = MagicMock()
    loop = asyncio.get_running_loop()
    with (
        patch.object(
            loop, "getaddrinfo", AsyncMock(return_value=[(2, 2, 17, "", ("192.0.2.1", 5684))])
        ),
        patch.object(loop, "sock_connect", AsyncMock()),
        patch("custom_components.kalfire_gi.gi.transport.socket.socket", return_value=fake_socket),
        patch("custom_components.kalfire_gi.gi.transport.SSL.Connection", return_value=fake_ssl),
        patch(
            "custom_components.kalfire_gi.gi.transport.crypto.dump_certificate",
            return_value=b"example-public-certificate",
        ),
    ):
        with pytest.raises(CertificateChanged):
            await transport.connect()
    fake_ssl.send.assert_not_called()
    fake_socket.close.assert_called_once()
    assert transport._ssl is None and transport._socket is None


async def test_accepted_pin_connects_without_sending_application_data():
    certificate = b"example-public-certificate"
    pin = hashlib.sha256(certificate).hexdigest()
    transport = DtlsTransport("fireplace.invalid", fingerprint=pin)
    transport._drive = AsyncMock()
    fake_socket = MagicMock()
    fake_ssl = MagicMock()
    loop = asyncio.get_running_loop()
    with (
        patch.object(
            loop, "getaddrinfo", AsyncMock(return_value=[(2, 2, 17, "", ("192.0.2.1", 5684))])
        ),
        patch.object(loop, "sock_connect", AsyncMock()),
        patch("custom_components.kalfire_gi.gi.transport.socket.socket", return_value=fake_socket),
        patch("custom_components.kalfire_gi.gi.transport.SSL.Connection", return_value=fake_ssl),
        patch(
            "custom_components.kalfire_gi.gi.transport.crypto.dump_certificate",
            return_value=certificate,
        ),
    ):
        assert await transport.connect() == pin
    fake_ssl.send.assert_not_called()
    transport.close()
    fake_socket.close.assert_called_once()


async def test_cancelled_connect_closes_socket():
    transport = DtlsTransport("fireplace.invalid")
    transport._drive = AsyncMock(side_effect=asyncio.CancelledError)
    fake_socket = MagicMock()
    loop = asyncio.get_running_loop()
    with (
        patch.object(
            loop, "getaddrinfo", AsyncMock(return_value=[(2, 2, 17, "", ("192.0.2.1", 5684))])
        ),
        patch.object(loop, "sock_connect", AsyncMock()),
        patch("custom_components.kalfire_gi.gi.transport.socket.socket", return_value=fake_socket),
        patch("custom_components.kalfire_gi.gi.transport.SSL.Connection", return_value=MagicMock()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await transport.connect()
    fake_socket.close.assert_called_once()

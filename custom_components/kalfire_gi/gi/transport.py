"""Async UDP/DTLS with pyOpenSSL's public memory-BIO interface.

We use a saved SHA256 leaf-certificate pin because the device uses a
private iQontrol CA. No token or application data is sent before pin validation.
Initial fingerprint discovery performs only a handshake. This is automatic trust
on first use, not verification of the manufacturer's CA or hostname.
"""

import asyncio
import hashlib
import hmac
import socket
import time
from collections.abc import Callable
from typing import TypeVar

from OpenSSL import SSL, crypto

from .errors import CannotConnect, CertificateChanged, ProtocolError

_T = TypeVar("_T")
DTLS_1_2 = 0xFEFD


class DtlsTransport:
    """A single serialized DTLS association to one IPv4 address/hostname."""

    def __init__(
        self, host: str, port: int = 5684, fingerprint: str | None = None, timeout: float = 8.0
    ) -> None:
        self.host = host
        self.port = port
        self.expected_fingerprint = fingerprint
        self.timeout = timeout
        self.fingerprint: str | None = None
        self._socket: socket.socket | None = None
        self._ssl: SSL.Connection | None = None

    async def connect(self) -> str:
        """Handshake and enforce the pin before returning a usable transport."""
        try:
            async with asyncio.timeout(self.timeout):
                loop = asyncio.get_running_loop()
                addresses = await loop.getaddrinfo(
                    self.host, self.port, family=socket.AF_INET, type=socket.SOCK_DGRAM
                )
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setblocking(False)
                await loop.sock_connect(self._socket, addresses[0][4])
                context = SSL.Context(SSL.DTLS_CLIENT_METHOD)
                context.set_min_proto_version(DTLS_1_2)
                context.set_max_proto_version(DTLS_1_2)
                context.set_cipher_list(b"ECDHE-ECDSA-AES256-GCM-SHA384")
                # CA verification is replaced by an saved leaf pin.
                context.set_verify(SSL.VERIFY_NONE, lambda *_: True)
                self._ssl = SSL.Connection(context, None)
                self._ssl.set_connect_state()
                self._ssl.set_ciphertext_mtu(1200)
                await self._drive(self._ssl.do_handshake, handshake=True)
                certificate = self._ssl.get_peer_certificate()
                if certificate is None:
                    raise ProtocolError("No peer certificate")
                self.fingerprint = hashlib.sha256(
                    crypto.dump_certificate(crypto.FILETYPE_ASN1, certificate)
                ).hexdigest()
                if self.expected_fingerprint and not hmac.compare_digest(
                    self.expected_fingerprint, self.fingerprint
                ):
                    raise CertificateChanged("The fireplace certificate has changed")
                return self.fingerprint
        except CertificateChanged, ProtocolError, asyncio.CancelledError:
            self.close()
            raise
        except (OSError, SSL.Error, TimeoutError) as err:
            self.close()
            raise CannotConnect("Could not establish the local DTLS session") from err

    async def _flush(self) -> None:
        """Send complete DTLS records as datagrams using the connected peer."""
        assert self._ssl is not None and self._socket is not None
        loop = asyncio.get_running_loop()
        while True:
            try:
                flight = self._ssl.bio_read(65536)
            except SSL.WantReadError:
                return
            offset = 0
            while offset < len(flight):
                if offset + 13 > len(flight):
                    raise ProtocolError("Truncated outbound DTLS record")
                end = offset + 13 + int.from_bytes(flight[offset + 11 : offset + 13], "big")
                if end > len(flight):
                    raise ProtocolError("Truncated outbound DTLS payload")
                await loop.sock_sendall(self._socket, flight[offset:end])
                offset = end

    async def _drive(self, operation: Callable[[], _T], *, handshake: bool = False) -> _T:
        assert self._ssl is not None and self._socket is not None
        deadline = time.monotonic() + self.timeout
        loop = asyncio.get_running_loop()
        while True:
            try:
                result = operation()
                await self._flush()
                return result
            except SSL.WantWriteError:
                await self._flush()
                await asyncio.sleep(0)
            except SSL.WantReadError:
                await self._flush()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError from None
                try:
                    async with asyncio.timeout(min(remaining, 0.5)):
                        packet = await loop.sock_recv(self._socket, 65536)
                    if not packet:
                        raise CannotConnect("Peer closed the DTLS session")
                    self._ssl.bio_write(packet)
                except TimeoutError:
                    if handshake:
                        # Handshake flights only; application requests are never retried.
                        self._ssl.DTLSv1_handle_timeout()
                        await self._flush()

    async def send(self, packet: bytes) -> None:
        if self.expected_fingerprint is None or self._ssl is None:
            raise ProtocolError("Application data requires an accepted certificate pin")
        await self._drive(lambda: self._ssl.send(packet))

    async def receive(self) -> bytes:
        if self._ssl is None:
            raise CannotConnect("No DTLS session")
        return await self._drive(lambda: self._ssl.recv(8192))

    def close(self) -> None:
        """Release locally; closing never sends an appliance command."""
        if self._socket is not None:
            self._socket.close()
        self._socket = None
        self._ssl = None

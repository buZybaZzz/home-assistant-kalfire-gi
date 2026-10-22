"""Small RFC 7252 codec for the Gi's observed Json endpoint.

No blockwise requests, Observe, discovery scans or application retransmissions.
"""

import secrets
from dataclasses import dataclass

from .errors import ProtocolError

MAX_DATAGRAM = 8192


def _nibble(value: int) -> tuple[int, bytes]:
    if value < 13:
        return value, b""
    if value < 269:
        return 13, bytes([value - 13])
    if value < 65805:
        return 14, (value - 269).to_bytes(2, "big")
    raise ValueError("CoAP option too long")


def _option(delta: int, value: bytes) -> bytes:
    d, de = _nibble(delta)
    n, ne = _nibble(len(value))
    return bytes([(d << 4) | n]) + de + ne + value


@dataclass(frozen=True)
class Message:
    """A fully validated datagram."""

    message_type: int
    code: int
    message_id: int
    token: bytes
    payload: bytes
    options: tuple[tuple[int, bytes], ...]


def request(payload: bytes, device_token: str) -> tuple[bytes, bytes, int]:
    """Build PUT /Json?token=...; the JSON method defines read vs command."""
    token = secrets.token_bytes(4)
    mid = secrets.randbelow(65536)
    packet = bytes([0x44, 3]) + mid.to_bytes(2, "big") + token
    packet += _option(11, b"Json")
    packet += _option(4, ("token=" + device_token).encode("ascii"))
    packet += b"\xff" + payload
    if len(packet) > 1100:
        raise ValueError("Request exceeds supported datagram size")
    return packet, token, mid


def decode(packet: bytes) -> Message:
    """Decode strictly, rejecting truncation, reserved encodings and blockwise."""
    if not 4 <= len(packet) <= MAX_DATAGRAM or packet[0] >> 6 != 1:
        raise ProtocolError("Invalid CoAP header")
    tkl = packet[0] & 15
    if tkl > 8 or 4 + tkl > len(packet):
        raise ProtocolError("Invalid CoAP token")
    offset = 4 + tkl
    options = []
    number = 0
    payload = b""

    def extend(nibble: int) -> int:
        nonlocal offset
        if nibble == 15:
            raise ProtocolError("Reserved CoAP option encoding")
        size = {13: 1, 14: 2}.get(nibble, 0)
        if offset + size > len(packet):
            raise ProtocolError("Truncated CoAP option")
        value = int.from_bytes(packet[offset : offset + size], "big")
        offset += size
        return value + {13: 13, 14: 269}.get(nibble, nibble)

    while offset < len(packet):
        header = packet[offset]
        offset += 1
        if header == 255:
            if offset == len(packet):
                raise ProtocolError("Empty CoAP payload marker")
            payload = packet[offset:]
            break
        number += extend(header >> 4)
        length = extend(header & 15)
        if offset + length > len(packet):
            raise ProtocolError("Truncated CoAP option value")
        value = packet[offset : offset + length]
        offset += length
        if number in (23, 27):
            raise ProtocolError("Blockwise CoAP response is not supported")
        if number % 2 and number not in (1, 3, 5, 7, 11, 15, 17, 35, 39):
            raise ProtocolError("Unknown critical CoAP option")
        options.append((number, value))
    return Message(
        (packet[0] >> 4) & 3,
        packet[1],
        int.from_bytes(packet[2:4], "big"),
        packet[4 : 4 + tkl],
        payload,
        tuple(options),
    )


def acknowledgement(mid: int) -> bytes:
    """ACK a separate CON response, not a new application request."""
    return b"\x60\x00" + mid.to_bytes(2, "big")

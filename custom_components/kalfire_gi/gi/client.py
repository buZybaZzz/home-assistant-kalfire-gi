"""Local Gi client: narrow named reads and explicit normal on/off commands."""

import asyncio
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

from OpenSSL import SSL

from .coap import acknowledgement, decode, request
from .errors import (
    AuthenticationError,
    CannotConnect,
    CommandUncertain,
    KalfireError,
    ProtocolError,
)
from .transport import DtlsTransport

READ_FIELDS = frozenset(
    {
        "sys.info.bmac",
        "sys.info.bsn",
        "sys.info.bsv",
        "modbus.1100",
        "modbus.1106",
        "modbus.1107",
        "modbus.1111",
        "sys.control.flame_height",
        "modbus.2007",
    }
)
STATE_NAMES = {
    0: "no_request",
    1: "waiting",
    2: "safety",
    3: "purge",
    4: "startup",
    5: "running",
    6: "lockout",
    7: "e_mode",
}


@dataclass(frozen=True)
class Snapshot:
    """A consistent polling result; flame height is a setting, not flame proof."""

    temperature: float
    state: int
    error_code: int
    status_bits: int
    flame_height: int
    spark: int | None = None


def validate_token(token: str) -> str:
    if re.fullmatch(r"[0-9a-f]{24}", token) is None:
        raise ValueError("Token must contain exactly 24 lowercase hex characters")
    return token


def validate_fingerprint(fingerprint: str) -> str:
    normalized = fingerprint.lower().replace(":", "").replace(" ", "")
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise ValueError("Certificate fingerprint must be SHA256")
    return normalized


class GiClient:
    """Serialize reads and commands; reconnecting never restores an on state."""

    def __init__(self, host: str, token: str, fingerprint: str, port: int = 5684) -> None:
        self.host = host
        self._token = validate_token(token)
        self.fingerprint = validate_fingerprint(fingerprint)
        self.port = port
        self._transport: DtlsTransport | None = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> DtlsTransport:
        if self._transport is None:
            transport = DtlsTransport(self.host, self.port, self.fingerprint)
            await transport.connect()
            self._transport = transport
        return self._transport

    async def _exchange(self, method: str, params: dict[str, Any]) -> Any:
        """One application request. Never retransmit a timed-out command."""
        request_id = secrets.randbelow(999)
        payload = json.dumps(
            {
                "id": request_id,
                "method": method,
                "params": params,
                **({"type": "integer"} if method == "rset" else {}),
            },
            separators=(",", ":"),
        ).encode()
        packet, token, mid = request(payload, self._token)
        transport = await self._connect()
        submitted = False
        try:
            async with asyncio.timeout(10):
                submitted = True  # A cancelled/failed send might already have reached the peer.
                await transport.send(packet)
                while True:
                    message = decode(await transport.receive())
                    if message.message_type == 3 and message.message_id == mid:
                        raise ProtocolError("Peer reset the CoAP request")
                    if message.code == 0:
                        continue  # Empty ACK; await a separate response, without resending.
                    if message.token != token:
                        continue
                    if message.message_type == 2 and message.message_id != mid:
                        continue
                    if message.message_type == 0:
                        await transport.send(acknowledgement(message.message_id))
                    if message.code == 129:
                        raise AuthenticationError("Pair the local client with the fireplace")
                    if message.code >> 5 != 2:
                        raise ProtocolError("The fireplace rejected the request")
                    try:
                        result = json.loads(message.payload)
                    except (ValueError, UnicodeError) as err:
                        raise ProtocolError("Invalid JSON response") from err
                    if (
                        not isinstance(result, dict)
                        or type(result.get("id")) is not int
                        or result["id"] != request_id
                    ):
                        raise ProtocolError("Unexpected JSON response ID")
                    if "error" in result or "result" not in result:
                        raise ProtocolError("The fireplace reported a protocol error")
                    return result["result"]
        except (OSError, SSL.Error, TimeoutError, KalfireError) as err:
            self.close()
            if (
                method in ("syscmd", "rset")
                and submitted
                and not isinstance(err, AuthenticationError)
            ):
                raise CommandUncertain(
                    "Command outcome unknown; check the fireplace before any new command"
                ) from err
            if isinstance(err, KalfireError):
                raise
            raise CannotConnect("The local request failed") from err
        except asyncio.CancelledError:
            self.close()
            raise

    async def _read(self, field: str) -> Any:
        if field not in READ_FIELDS:
            raise ValueError("Unsupported read field")
        result = await self._exchange("rget", {"name": field})
        if not isinstance(result, dict) or result.get("name") != field or "value" not in result:
            raise ProtocolError("Unexpected register response")
        return result["value"]

    async def read(self, field: str) -> Any:
        async with self._lock:
            return await self._read(field)

    async def identity(self) -> tuple[str, str]:
        async with self._lock:
            mac = await self._read("sys.info.bmac")
            firmware = await self._read("sys.info.bsv")
            if not isinstance(mac, str) or not re.fullmatch(
                r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac
            ):
                raise ProtocolError("Invalid device MAC")
            if not isinstance(firmware, str) or len(firmware) > 64:
                raise ProtocolError("Invalid firmware string")
            return mac.lower(), firmware

    async def snapshot(self, *, include_spark: bool = False) -> Snapshot:
        async with self._lock:
            values = [
                await self._read(field)
                for field in (
                    "modbus.1100",
                    "modbus.1111",
                    "modbus.1107",
                    "modbus.1106",
                    "sys.control.flame_height",
                )
            ]
            if any(type(value) is not int for value in values):
                raise ProtocolError("Unexpected register value type")
            if values[1] not in STATE_NAMES:
                raise ProtocolError("Unknown fireplace state")
            spark = await self._read("modbus.2007") if include_spark else None
            if include_spark and (type(spark) is not int or spark not in range(6)):
                raise ProtocolError("Invalid Spark value")
            return Snapshot(values[0] / 10, *values[1:], spark=spark)

    async def set_level(self, key: str, value: int) -> None:
        """Set only tested normal levels, while running without a reported fault."""
        fields = {"flame_height": ("sys.control.flame_height", 1), "spark": ("modbus.2007", 0)}
        if key not in fields or type(value) is not int:
            raise ValueError("Unsupported setting or non-integer level")
        field, minimum = fields[key]
        if not minimum <= value <= 5:
            raise ValueError("Level outside supported range")
        async with self._lock:
            fault = await self._read("modbus.1107")
            state = await self._read("modbus.1111")
            if type(fault) is not int or type(state) is not int or fault != 0 or state != 5:
                raise KalfireError("Settings require a running fireplace without a reported fault")
            result = await self._exchange("rset", {"name": field, "value": value})
            if result != "success":
                raise CommandUncertain(
                    "Setting was not confirmed; check before issuing another command"
                )

    async def start(self) -> None:
        """Normal app syscmd mode=1; no reset or direct valve writes."""
        async with self._lock:
            fault = await self._read("modbus.1107")
            state = await self._read("modbus.1111")
            if type(fault) is not int or type(state) is not int:
                raise ProtocolError("Invalid pre-start status")
            if fault != 0 or state == 6:
                raise KalfireError(
                    "Fireplace reports a fault; resolve it using the official controls"
                )
            if state == 5:
                return  # Already running: do not send a duplicate start.
            if state != 0:
                raise KalfireError("Fireplace is not idle; no start sent")
            result = await self._exchange("syscmd", {"mode": 1})
            if result != "success":
                raise CommandUncertain("Start response was not success; do not retry automatically")

    async def stop(self) -> None:
        """Normal app syscmd mode=0. Only runs after an explicit off action."""
        async with self._lock:
            result = await self._exchange("syscmd", {"mode": 0})
            if result != "success":
                raise CommandUncertain("Stop response was not success; check the fireplace")

    def close(self) -> None:
        if self._transport:
            self._transport.close()
        self._transport = None

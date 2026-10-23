"""Protocol validation and exact wire semantics, with no real network access."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kalfire_gi.gi import GiClient
from custom_components.kalfire_gi.gi.client import validate_fingerprint, validate_token
from custom_components.kalfire_gi.gi.coap import acknowledgement, decode, request
from custom_components.kalfire_gi.gi.errors import (
    AuthenticationError,
    CommandUncertain,
    KalfireError,
    ProtocolError,
)

TOKEN = "a" * 24
PIN = "b" * 64


def test_request_format():
    data, token, mid = request(b'{"method":"rget"}', TOKEN)
    message = decode(data)
    assert message.code == 3
    assert message.token == token
    assert message.message_id == mid
    assert message.options == ((11, b"Json"), (15, b"token=" + TOKEN.encode()))
    assert message.payload == b'{"method":"rget"}'
    assert acknowledgement(mid) == b"\x60\x00" + mid.to_bytes(2, "big")


@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x40",
        b"\x00\x45\x00\x01",
        b"\x49\x45\x00\x01",
        b"\x44\x45\x00\x01a",
        b"\x40\x45\x00\x01\xff",
        b"\x40\x45\x00\x01\xfd",
        b"\x40\x45\x00\x01\x1e\x00",
        b"\x40\x45\x00\x01\x12a",
        b"\x40\x45\x00\x01\xb0\xc1\x00",
    ],
)
def test_reject_malformed_or_blockwise(packet):
    with pytest.raises(ProtocolError):
        decode(packet)


@pytest.mark.parametrize("token", ["", "A" * 24, "a" * 23, "a" * 25, "g" * 24])
def test_invalid_token(token):
    with pytest.raises(ValueError):
        validate_token(token)


def test_fingerprint_normalization():
    assert validate_fingerprint(":".join(["BB"] * 32)) == PIN
    with pytest.raises(ValueError):
        validate_fingerprint("bad")


@pytest.fixture
def client():
    return GiClient("fireplace.invalid", TOKEN, PIN)


@pytest.mark.parametrize(
    "state,fault", [(2, 0), (3, 0), (4, 0), (6, 0), (0, 4), (False, 0), (0, True)]
)
async def test_start_rejects_fault_or_transition(client, state, fault):
    client._read = AsyncMock(side_effect=[fault, state])
    client._exchange = AsyncMock()
    with pytest.raises(KalfireError):
        await client.start()
    client._exchange.assert_not_awaited()


async def test_start_is_one_normal_command(client):
    client._read = AsyncMock(side_effect=[0, 0])
    client._exchange = AsyncMock(return_value="success")
    await client.start()
    client._exchange.assert_awaited_once_with("syscmd", {"mode": 1})


async def test_running_does_not_send_duplicate_start(client):
    client._read = AsyncMock(side_effect=[0, 5])
    client._exchange = AsyncMock()
    await client.start()
    client._exchange.assert_not_awaited()


async def test_stop_is_normal_mode_zero(client):
    client._exchange = AsyncMock(return_value="success")
    await client.stop()
    client._exchange.assert_awaited_once_with("syscmd", {"mode": 0})


async def test_snapshot_is_only_reads(client):
    client._exchange = AsyncMock(
        side_effect=[
            {"name": name, "value": value}
            for name, value in [
                ("modbus.1100", 207),
                ("modbus.1111", 5),
                ("modbus.1107", 0),
                ("modbus.1106", 2415),
                ("sys.control.flame_height", 0),
            ]
        ]
    )
    result = await client.snapshot()
    assert result.temperature == 20.7 and result.state == 5
    assert all(call.args[0] == "rget" for call in client._exchange.await_args_list)


async def test_arbitrary_register_rejected(client):
    client._exchange = AsyncMock()
    with pytest.raises(ValueError):
        await client.read("modbus.2002")
    client._exchange.assert_not_awaited()


@pytest.mark.parametrize("method,expected", [("syscmd", CommandUncertain), ("rget", KalfireError)])
async def test_timeout_never_retransmits(client, method, expected):
    transport = MagicMock()
    transport.send = AsyncMock()
    transport.receive = AsyncMock(side_effect=TimeoutError)
    client._connect = AsyncMock(return_value=transport)
    client._transport = transport
    with pytest.raises(expected):
        await client._exchange(
            method, {"mode": 1} if method == "syscmd" else {"name": "modbus.1100"}
        )
    transport.send.assert_awaited_once()
    transport.close.assert_called_once()
    assert client._transport is None


async def test_json_correlation_checked(client):
    transport = MagicMock(send=AsyncMock())
    transport.receive = AsyncMock(
        return_value=b'\x64\x45\x00\x01abcd\xff{"id":42,"result":"success"}'
    )
    client._connect = AsyncMock(return_value=transport)
    with (
        patch(
            "custom_components.kalfire_gi.gi.client.request", return_value=(b"request", b"abcd", 1)
        ),
        patch("custom_components.kalfire_gi.gi.client.secrets.randbelow", return_value=41),
    ):
        with pytest.raises(ProtocolError):
            await client._exchange("rget", {"name": "modbus.1100"})


async def test_empty_ack_then_separate_response(client):
    transport = MagicMock(send=AsyncMock())
    result = json.dumps({"id": 41, "result": {"value": 207}}).encode()
    transport.receive = AsyncMock(
        side_effect=[b"\x60\x00\x00\x01", b"\x44\x45\x00\x02abcd\xff" + result]
    )
    client._connect = AsyncMock(return_value=transport)
    with (
        patch(
            "custom_components.kalfire_gi.gi.client.request", return_value=(b"request", b"abcd", 1)
        ),
        patch("custom_components.kalfire_gi.gi.client.secrets.randbelow", return_value=41),
    ):
        assert await client._exchange("rget", {}) == {"value": 207}
    assert [call.args[0] for call in transport.send.await_args_list] == [
        b"request",
        acknowledgement(2),
    ]


async def test_unauthorized_not_misreported_as_success(client):
    transport = MagicMock(send=AsyncMock(), receive=AsyncMock(return_value=b"\x64\x81\x00\x01abcd"))
    client._connect = AsyncMock(return_value=transport)
    with patch(
        "custom_components.kalfire_gi.gi.client.request", return_value=(b"request", b"abcd", 1)
    ):
        with pytest.raises(AuthenticationError):
            await client._exchange("rget", {})


@pytest.mark.parametrize(
    "key,value",
    [
        ("flame_height", 0),
        ("flame_height", 6),
        ("spark", -1),
        ("spark", 6),
        ("spark", True),
        ("spark", 2.5),
        ("gasValve1", 1),
    ],
)
async def test_invalid_setting_never_touches_network(client, key, value):
    client._read = AsyncMock()
    client._exchange = AsyncMock()
    with pytest.raises(ValueError):
        await client.set_level(key, value)
    client._read.assert_not_awaited()
    client._exchange.assert_not_awaited()


@pytest.mark.parametrize("state,fault", [(0, 0), (4, 0), (5, 1), (6, 0), (True, 0)])
async def test_setting_requires_running_without_fault(client, state, fault):
    client._read = AsyncMock(side_effect=[fault, state])
    client._exchange = AsyncMock()
    with pytest.raises(KalfireError):
        await client.set_level("spark", 5)
    client._exchange.assert_not_awaited()


@pytest.mark.parametrize(
    "key,value,field",
    [
        ("flame_height", 1, "sys.control.flame_height"),
        ("flame_height", 5, "sys.control.flame_height"),
        ("spark", 0, "modbus.2007"),
        ("spark", 5, "modbus.2007"),
    ],
)
async def test_level_sends_one_allowed_write(client, key, value, field):
    client._read = AsyncMock(side_effect=[0, 5])
    client._exchange = AsyncMock(return_value="success")
    await client.set_level(key, value)
    client._exchange.assert_awaited_once_with("rset", {"name": field, "value": value})


async def test_rset_wire_type_and_uncertain_timeout(client):
    transport = MagicMock(send=AsyncMock(), receive=AsyncMock(side_effect=TimeoutError))
    client._connect = AsyncMock(return_value=transport)
    client._transport = transport
    with pytest.raises(CommandUncertain):
        await client._exchange("rset", {"name": "modbus.2007", "value": 5})
    transport.send.assert_awaited_once()
    payload = json.loads(decode(transport.send.await_args.args[0]).payload)
    assert payload["type"] == "integer"
    transport.close.assert_called_once()

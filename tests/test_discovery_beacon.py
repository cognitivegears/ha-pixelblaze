"""Tests for the defensive UDP beacon listener."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pixelblaze.const import BEACON_TYPE_DEVICE
from custom_components.pixelblaze.discovery import (
    PixelblazeBeaconListener,
    _parse_beacon,
)


def test_parse_beacon_valid() -> None:
    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 0x12345678, 1234) + b"Lobby\x00"
    info = _parse_beacon(payload)
    assert info is not None
    assert info["sender_id"] == 0x12345678
    assert info["name"] == "Lobby"


def test_parse_beacon_wrong_type() -> None:
    payload = struct.pack("<III", 99, 1, 1)
    assert _parse_beacon(payload) is None


def test_parse_beacon_too_short() -> None:
    assert _parse_beacon(b"\x00\x00") is None


async def test_listener_bind_failure_disables_gracefully(hass) -> None:
    """An OSError on bind must not crash setup."""
    listener = PixelblazeBeaconListener(hass)
    with patch(
        "socket.socket",
        side_effect=OSError("Address already in use"),
    ):
        ok = await listener.async_start()
    assert ok is False
    assert listener.enabled is False


async def test_handle_packet_dedupes(hass) -> None:
    listener = PixelblazeBeaconListener(hass)
    hass.config_entries.flow.async_init = AsyncMock()  # type: ignore[method-assign]
    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 0xABCD, 0)
    listener.handle_packet(payload, ("192.168.1.42", 1889))
    listener.handle_packet(payload, ("192.168.1.42", 1889))
    # Allow scheduled tasks to run.
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_init.await_count == 1


async def test_handle_packet_invalid_does_not_raise(hass) -> None:
    listener = PixelblazeBeaconListener(hass)
    listener.handle_packet(b"junk", ("1.2.3.4", 1889))
    # No exception is the assertion.

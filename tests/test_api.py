"""Tests for the PixelblazeClient async wrapper."""

from __future__ import annotations

import pytest

from custom_components.pixelblaze.api import (
    PixelblazeClient,
    PixelblazeConnectionError,
    _translate_exceptions,
)


async def test_connect_and_fetch_state(hass) -> None:
    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    state = await client.async_fetch_state(None)
    assert state.pixelblaze_id == "pb-test-1"
    assert state.name == "Test Pixelblaze"
    assert state.version == "3.30"
    assert state.fps == 60.0
    assert state.led_count == 64
    assert state.brightness == 0.5
    assert state.active_pattern_id == "ptn-001"
    assert state.active_pattern_name == "Rainbow"
    assert "sliderSpeed" in state.active_controls
    await client.async_close()


async def test_set_brightness_clamps(hass) -> None:
    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    await client.async_set_brightness(2.5)
    state = await client.async_fetch_state(None)
    assert state.brightness == 1.0

    await client.async_set_brightness(-0.5)
    state = await client.async_fetch_state(None)
    assert state.brightness == 0.0
    await client.async_close()


async def test_set_pattern(hass) -> None:
    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    await client.async_set_pattern("ptn-002")
    state = await client.async_fetch_state(None)
    assert state.active_pattern_id == "ptn-002"
    assert state.active_pattern_name == "Sparkles"
    await client.async_close()


async def test_translate_websocket_error_is_connection_error() -> None:
    from websocket import WebSocketException

    err = _translate_exceptions(WebSocketException("bye"))
    assert isinstance(err, PixelblazeConnectionError)


async def test_translate_oserror_is_connection_error() -> None:
    err = _translate_exceptions(OSError("network unreachable"))
    assert isinstance(err, PixelblazeConnectionError)


async def test_translate_connection_refused_is_connection_error() -> None:
    err = _translate_exceptions(ConnectionRefusedError("nope"))
    assert isinstance(err, PixelblazeConnectionError)


async def test_translate_value_error_is_command_error() -> None:
    from custom_components.pixelblaze.api import PixelblazeCommandError

    err = _translate_exceptions(ValueError("bad arg"))
    assert isinstance(err, PixelblazeCommandError)


async def test_close_is_idempotent(hass) -> None:
    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    await client.async_close()
    # Second close should be a no-op, not raise.
    await client.async_close()

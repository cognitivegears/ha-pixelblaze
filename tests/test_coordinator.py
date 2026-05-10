"""Tests for the Pixelblaze DataUpdateCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pixelblaze.api import PixelblazeClient, PixelblazeConnectionError
from custom_components.pixelblaze.const import DOMAIN
from custom_components.pixelblaze.coordinator import PixelblazeDataUpdateCoordinator


async def _build_coordinator(hass) -> PixelblazeDataUpdateCoordinator:
    from homeassistant.config_entries import ConfigEntry

    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    entry = ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test",
        data={"host": "1.2.3.4"},
        source="user",
        unique_id="pb-test-1",
        options={},
        discovery_keys={},
        subentries_data=None,
    )
    return PixelblazeDataUpdateCoordinator(hass, entry, client)


async def test_first_refresh_populates_state(hass) -> None:
    coord = await _build_coordinator(hass)
    await coord.async_refresh()
    assert coord.last_update_success
    assert coord.data is not None
    assert coord.data.active_pattern_name == "Rainbow"


async def test_connection_error_marks_failure(hass) -> None:
    coord = await _build_coordinator(hass)
    with patch.object(
        coord.client,
        "async_fetch_state",
        side_effect=PixelblazeConnectionError("down"),
    ):
        await coord.async_refresh()
    assert not coord.last_update_success


async def test_set_brightness_optimistic_update(hass) -> None:
    """async_set_brightness should update local state immediately (no debounce)."""
    coord = await _build_coordinator(hass)
    await coord.async_refresh()
    assert coord.data is not None
    await coord.async_set_brightness(0.25)
    # Local state reflects the new value before the next poll fires.
    assert coord.data.brightness == 0.25

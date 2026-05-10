"""Tests for the custom services."""

from __future__ import annotations

from custom_components.pixelblaze.const import (
    DOMAIN,
    SERVICE_NEXT_PATTERN,
    SERVICE_SET_PATTERN,
    SERVICE_SET_VARIABLE,
)


async def test_set_variable_service(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_VARIABLE,
        {"device_id": device.id, "name": "speed", "value": 0.7},
        blocking=True,
    )
    pb = entry.runtime_data.client._pb  # type: ignore[attr-defined]
    assert pb.last_set_variables == {"speed": 0.7}


async def test_set_pattern_service_by_name(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PATTERN,
        {"device_id": device.id, "pattern": "Sparkles"},
        blocking=True,
    )
    pb = entry.runtime_data.client._pb  # type: ignore[attr-defined]
    assert pb.getActivePattern() == "ptn-002"


async def test_set_pattern_service_by_id(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PATTERN,
        {"device_id": device.id, "pattern": "ptn-003"},
        blocking=True,
    )
    pb = entry.runtime_data.client._pb  # type: ignore[attr-defined]
    assert pb.getActivePattern() == "ptn-003"


async def test_next_pattern_service(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_NEXT_PATTERN,
        {"device_id": device.id},
        blocking=True,
    )
    pb = entry.runtime_data.client._pb  # type: ignore[attr-defined]
    assert pb.next_called is True

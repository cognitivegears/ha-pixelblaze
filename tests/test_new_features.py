"""Tests for color-picker light, activate_scene, and get_variables."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.pixelblaze.const import (
    DOMAIN,
    SERVICE_ACTIVATE_SCENE,
    SERVICE_GET_VARIABLES,
)
from tests.conftest import FakePixelblaze

# ---- Color-picker light entity ------------------------------------------


@pytest.fixture
def with_color_picker() -> Any:
    """Override active_controls so the active pattern advertises an HSV picker."""
    FakePixelblaze.state_overrides["activeControls"] = {
        "sliderSpeed": 0.5,
        "hsvPickerColor": [0.5, 1.0, 0.8],  # cyan, full sat, 80% V
    }
    yield
    FakePixelblaze.state_overrides.pop("activeControls", None)


async def test_color_picker_light_appears(hass, with_color_picker, setup_entry) -> None:
    state = hass.states.get("light.test_pixelblaze_hsvpickercolor")
    assert state is not None
    assert state.state == "on"
    # 0.8 * 255 ≈ 204
    assert state.attributes.get("brightness") == round(0.8 * 255)
    hs = state.attributes.get("hs_color")
    assert hs is not None
    assert hs[0] == pytest.approx(180.0, abs=0.5)  # 0.5 * 360
    assert hs[1] == pytest.approx(100.0, abs=0.5)  # 1.0 * 100


async def test_color_picker_light_set_color(hass, with_color_picker, setup_entry) -> None:
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            "entity_id": "light.test_pixelblaze_hsvpickercolor",
            "hs_color": [120.0, 50.0],
            "brightness": 128,
        },
        blocking=True,
    )
    pb = setup_entry.runtime_data.client._pb
    assert pb.last_set_color_control is not None
    name, color, _save = pb.last_set_color_control
    assert name == "hsvPickerColor"
    assert color[0] == pytest.approx(120.0 / 360.0, abs=0.001)
    assert color[1] == pytest.approx(0.5, abs=0.01)
    assert color[2] == pytest.approx(128 / 255.0, abs=0.01)


async def test_color_picker_light_turn_off_sets_v_zero(
    hass, with_color_picker, setup_entry
) -> None:
    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": "light.test_pixelblaze_hsvpickercolor"},
        blocking=True,
    )
    pb = setup_entry.runtime_data.client._pb
    assert pb.last_set_color_control is not None
    name, color, _save = pb.last_set_color_control
    assert name == "hsvPickerColor"
    # H and S preserved, V driven to 0.
    assert color[0] == pytest.approx(0.5, abs=0.001)
    assert color[1] == pytest.approx(1.0, abs=0.001)
    assert color[2] == 0.0


async def test_color_picker_unavailable_without_control(hass, setup_entry) -> None:
    """No hsvPicker control on the default test pattern -> entity not added."""
    state = hass.states.get("light.test_pixelblaze_hsvpickercolor")
    assert state is None


# ---- activate_scene service ----------------------------------------------


async def test_activate_scene_atomic(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_SCENE,
        {
            "device_id": device.id,
            "pattern": "Sparkles",
            "brightness": 0.4,
            "variables": {"speed": 0.7},
        },
        blocking=True,
    )
    pb = entry.runtime_data.client._pb
    assert pb.getActivePattern() == "ptn-002"  # Sparkles
    assert pb.getBrightnessSlider() == pytest.approx(0.4)
    assert pb.last_set_variables == {"speed": 0.7}


async def test_activate_scene_requires_at_least_one_field(hass, setup_entry_with_device) -> None:
    _entry, device = setup_entry_with_device
    with pytest.raises(Exception):  # vol.MultipleInvalid wrapped by HA
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ACTIVATE_SCENE,
            {"device_id": device.id},
            blocking=True,
        )


async def test_activate_scene_brightness_only(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_SCENE,
        {"device_id": device.id, "brightness": 0.1},
        blocking=True,
    )
    pb = entry.runtime_data.client._pb
    assert pb.getBrightnessSlider() == pytest.approx(0.1)


async def test_activate_scene_unknown_pattern_errors(hass, setup_entry_with_device) -> None:
    _entry, device = setup_entry_with_device
    with pytest.raises(Exception):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ACTIVATE_SCENE,
            {"device_id": device.id, "pattern": "DoesNotExist"},
            blocking=True,
        )


async def test_activate_scene_with_sequencer_mode(hass, setup_entry_with_device) -> None:
    entry, device = setup_entry_with_device
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_SCENE,
        {
            "device_id": device.id,
            "pattern": "Fire",
            "sequencer_mode": "shuffle_all",
        },
        blocking=True,
    )
    pb = entry.runtime_data.client._pb
    assert pb.getActivePattern() == "ptn-003"
    assert pb._sequencer_mode == 1  # shuffle


# ---- get_variables service -----------------------------------------------


async def test_get_variables_returns_response(hass, setup_entry_with_device) -> None:
    _entry, device = setup_entry_with_device
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_VARIABLES,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert "devices" in response
    assert device.id in response["devices"]
    # FakePixelblaze.getActiveVariables() returns {"hue": 0.5}
    assert response["devices"][device.id] == {"hue": 0.5}


async def test_get_variables_unknown_device(hass, setup_entry_with_device) -> None:
    with pytest.raises(Exception):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_VARIABLES,
            {"device_id": "no-such-device-id"},
            blocking=True,
            return_response=True,
        )

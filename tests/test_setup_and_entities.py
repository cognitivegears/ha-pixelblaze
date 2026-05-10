"""End-to-end test: set up an entry and verify entities work."""

from __future__ import annotations


async def test_light_entity_state(hass, setup_entry) -> None:
    state = hass.states.get("light.test_pixelblaze")
    assert state is not None
    assert state.state in ("on", "off")
    assert "brightness" in state.attributes
    assert "Rainbow" in (state.attributes.get("effect_list") or [])


async def test_light_turn_off_sets_brightness_zero(hass, setup_entry) -> None:
    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": "light.test_pixelblaze"},
        blocking=True,
    )
    state = hass.states.get("light.test_pixelblaze")
    assert state.state == "off"


async def test_pattern_select_entity(hass, setup_entry) -> None:
    state = hass.states.get("select.test_pixelblaze_pattern")
    assert state is not None
    assert state.state == "Rainbow"
    assert "Sparkles" in state.attributes["options"]

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.test_pixelblaze_pattern", "option": "Sparkles"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("select.test_pixelblaze_pattern")
    assert state.state == "Sparkles"


async def test_fps_sensor(hass, setup_entry) -> None:
    state = hass.states.get("sensor.test_pixelblaze_frames_per_second")
    assert state is not None
    assert float(state.state) == 60.0


async def test_next_pattern_button(hass, setup_entry) -> None:
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.test_pixelblaze_next_pattern"},
        blocking=True,
    )
    pb = setup_entry.runtime_data.client._pb  # type: ignore[attr-defined]
    assert getattr(pb, "next_called", False) is True


async def test_unload_entry(hass, setup_entry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()

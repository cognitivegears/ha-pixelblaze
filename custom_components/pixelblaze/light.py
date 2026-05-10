"""Light platform for Pixelblaze.

Two flavors of light entity:

* :class:`PixelblazeLight` — the device-level light (brightness slider plus
  pattern as ``effect``). One per device.
* :class:`PixelblazeColorPickerLight` — one per ``hsvPicker*`` control
  exported by the active pattern. Surfaces the pattern's color picker as a
  native HS-colored light so users get a real swatch in the UI rather than
  having to call ``pixelblaze.set_color_control`` from YAML.

Color-picker entities are added dynamically as patterns expose new controls
(mirroring the ``number`` platform). They become ``unavailable`` rather than
disappearing when the active pattern changes, so users keep history and
automations targeting them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import callback

from .entity import PixelblazeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PixelblazeConfigEntry
    from .coordinator import PixelblazeDataUpdateCoordinator

# Per-device serialization happens at PixelblazeClient._lock; HA-level platform
# parallelism would only add a redundant queue. Explicit no-limit.
PARALLEL_UPDATES = 0


def _is_color_picker(name: str, value: Any) -> bool:
    """True when ``name``/``value`` look like an HSV-picker control.

    RGB pickers exist on the device too but HA's ColorMode.HS round-trips
    HSV cleanly — RGB pickers are deliberately deferred to ``set_color_control``
    until we have a use case that justifies the extra surface.
    """
    if not isinstance(value, list | tuple) or len(value) < 3:
        return False
    return name.lower().startswith("hsvpicker")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixelblazeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([PixelblazeLight(coordinator)])

    known_pickers: set[str] = set()

    @callback
    def _refresh_pickers() -> None:
        state = coordinator.data
        if state is None:
            return
        new_pickers = {
            name for name, value in state.active_controls.items() if _is_color_picker(name, value)
        }
        added = new_pickers - known_pickers
        if added:
            async_add_entities(
                PixelblazeColorPickerLight(coordinator, name) for name in sorted(added)
            )
            known_pickers.update(added)

    _refresh_pickers()
    entry.async_on_unload(coordinator.async_add_listener(_refresh_pickers))


class PixelblazeLight(PixelblazeEntity, LightEntity):
    """A single light entity exposing brightness + pattern as effect.

    The light's effect mirrors the ``select.pattern`` entity — same backing
    state, same write target, surfaced two ways for convenience. Effect
    labels disambiguate duplicate pattern names by appending an id prefix
    (see ``PixelblazeState.find_pattern_id``).
    """

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_features = LightEntityFeature.EFFECT
    # No translation_key: with has_entity_name=True and name=None, the entity
    # takes the device's name. Setting a translation_key here would force HA
    # to look up `entity.light.<key>.name` which doesn't exist.
    _attr_name = None

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_light"
        self._last_brightness: float = 1.0

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        if state is None:
            return False
        return not state.paused and state.brightness > 0.0

    @property
    def brightness(self) -> int | None:
        state = self.coordinator.data
        if state is None:
            return None
        return round(max(0.0, min(1.0, state.brightness)) * 255)

    @property
    def effect(self) -> str | None:
        state = self.coordinator.data
        if not state or not state.active_pattern_id:
            return None
        # Return the disambiguated label so the UI shows which "Sparkles" is
        # actually active when names collide.
        for label, pid in state.pattern_label_to_id.items():
            if pid == state.active_pattern_id:
                return label
        return state.active_pattern_name

    @property
    def effect_list(self) -> list[str] | None:
        state = self.coordinator.data
        if not state:
            return None
        return sorted(state.pattern_label_to_id.keys())

    async def async_turn_on(self, **kwargs: Any) -> None:
        coordinator = self.coordinator
        state = coordinator.data
        if state and state.brightness > 0.0:
            self._last_brightness = state.brightness

        if ATTR_BRIGHTNESS in kwargs:
            target = float(kwargs[ATTR_BRIGHTNESS]) / 255.0
        elif state and state.brightness > 0.0:
            target = state.brightness
        else:
            target = self._last_brightness if self._last_brightness > 0 else 1.0

        await coordinator.async_set_brightness(target)
        if state and state.paused:
            await coordinator.async_set_paused(False)

        effect = kwargs.get(ATTR_EFFECT)
        if effect and state is not None:
            pid = state.find_pattern_id(effect)
            if pid is not None:
                await coordinator.async_set_pattern(pid)

    async def async_turn_off(self, **_: Any) -> None:
        state = self.coordinator.data
        if state and state.brightness > 0.0:
            self._last_brightness = state.brightness
        await self.coordinator.async_set_brightness(0.0)


class PixelblazeColorPickerLight(PixelblazeEntity, LightEntity):
    """A pattern's HSV color-picker control surfaced as an HS light.

    The Pixelblaze stores hsvPicker values as ``[h, s, v]`` floats in 0..1.
    HA's ColorMode.HS uses ``(hue 0-360, sat 0-100)`` for color and 0-255 for
    brightness — this entity translates both directions and treats the V
    channel as the light's brightness.

    Unavailable when the active pattern doesn't expose this control.
    """

    _attr_supported_color_modes = {ColorMode.HS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator, control_name: str) -> None:
        super().__init__(coordinator)
        self._control_name = control_name
        self._attr_unique_id = f"{self._device_id}_color_{control_name}"
        self._attr_name = control_name
        # When the user turns the picker off (V=0) we remember the prior V so
        # ``turn_on`` without a brightness arg restores it instead of jumping
        # to full brightness or staying invisible.
        self._last_v: float = 1.0

    def _current_hsv(self) -> tuple[float, float, float] | None:
        state = self.coordinator.data
        if state is None:
            return None
        value = state.active_controls.get(self._control_name)
        if not isinstance(value, list | tuple) or len(value) < 3:
            return None
        try:
            h = float(value[0])
            s = float(value[1])
            v = float(value[2])
        except (TypeError, ValueError):
            return None
        return (
            max(0.0, min(1.0, h)),
            max(0.0, min(1.0, s)),
            max(0.0, min(1.0, v)),
        )

    @property
    def available(self) -> bool:
        if self.coordinator.data is None:
            return False
        return self._current_hsv() is not None

    @property
    def is_on(self) -> bool:
        hsv = self._current_hsv()
        return hsv is not None and hsv[2] > 0.0

    @property
    def hs_color(self) -> tuple[float, float] | None:
        hsv = self._current_hsv()
        if hsv is None:
            return None
        h, s, _ = hsv
        return (h * 360.0, s * 100.0)

    @property
    def brightness(self) -> int | None:
        hsv = self._current_hsv()
        if hsv is None:
            return None
        return round(hsv[2] * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        cur = self._current_hsv() or (0.0, 1.0, 1.0)
        h, s, v = cur

        if v > 0.0:
            self._last_v = v

        if ATTR_HS_COLOR in kwargs:
            new_h, new_s = kwargs[ATTR_HS_COLOR]
            h = max(0.0, min(1.0, float(new_h) / 360.0))
            s = max(0.0, min(1.0, float(new_s) / 100.0))

        if ATTR_BRIGHTNESS in kwargs:
            v = max(0.0, min(1.0, float(kwargs[ATTR_BRIGHTNESS]) / 255.0))
        elif v <= 0.0:
            v = self._last_v if self._last_v > 0.0 else 1.0

        await self.coordinator.async_set_color_control(self._control_name, [h, s, v])

    async def async_turn_off(self, **_: Any) -> None:
        cur = self._current_hsv()
        if cur is None:
            return
        h, s, v = cur
        if v > 0.0:
            self._last_v = v
        await self.coordinator.async_set_color_control(self._control_name, [h, s, 0.0])

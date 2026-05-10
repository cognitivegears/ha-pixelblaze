"""Number platform — dynamic per-pattern slider controls.

Pixelblaze patterns can expose typed UI controls via ``exportControl``. For v1
we map *slider* controls (scalar 0..1) to ``number`` entities. Color pickers
are surfaced via the ``pixelblaze.set_color_control`` service rather than as
entities, since HA does not have a native color-picker number type.

Entities are added dynamically as patterns are activated. Removed-but-known
controls remain registered (HA shows them as ``unavailable``) so users don't
lose history when switching patterns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .entity import PixelblazeEntity

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PixelblazeConfigEntry
    from .coordinator import PixelblazeDataUpdateCoordinator

# Per-device serialization happens at PixelblazeClient._lock; HA-level platform
# parallelism would only add a redundant queue. Explicit no-limit.
PARALLEL_UPDATES = 0


def _is_slider_control(name: str, value: Any) -> bool:
    """Return True if a control entry from getActiveControls is a scalar slider."""
    if not isinstance(value, int | float):
        return False
    lname = name.lower()
    return not lname.startswith(("hsvpicker", "rgbpicker"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixelblazeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _refresh() -> None:
        state = coordinator.data
        if state is None:
            return
        new_controls = {
            name for name, value in state.active_controls.items() if _is_slider_control(name, value)
        }
        added = new_controls - known
        if added:
            async_add_entities(PixelblazeControlNumber(coordinator, name) for name in sorted(added))
            known.update(added)

    # Add entities for whatever the active pattern exposes right now.
    _refresh()
    # Watch for new control names appearing when the active pattern changes.
    entry.async_on_unload(coordinator.async_add_listener(_refresh))


class PixelblazeControlNumber(PixelblazeEntity, NumberEntity):
    """A scalar slider exposed by the active Pixelblaze pattern."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1.0
    _attr_native_step = 0.01

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator, control_name: str) -> None:
        super().__init__(coordinator)
        self._control_name = control_name
        self._attr_unique_id = f"{self._device_id}_control_{control_name}"
        self._attr_name = control_name

    @property
    def available(self) -> bool:
        state = self.coordinator.data
        if state is None:
            return False
        return self._control_name in state.active_controls

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.data
        if state is None:
            return None
        value = state.active_controls.get(self._control_name)
        if isinstance(value, int | float):
            return float(value)
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_active_control(
            self._control_name, max(0.0, min(1.0, float(value)))
        )

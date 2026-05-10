"""Switch platform — sequencer enable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory

from .const import SEQUENCER_MODE_OFF, SEQUENCER_MODE_SHUFFLE
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixelblazeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([PixelblazeSequencerSwitch(coordinator)])


class PixelblazeSequencerSwitch(PixelblazeEntity, SwitchEntity):
    """Toggles the sequencer between Off and Shuffle All."""

    _attr_translation_key = "sequencer"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:shuffle-variant"

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_sequencer_enabled"

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        return bool(
            state and state.sequencer_mode != SEQUENCER_MODE_OFF and state.sequencer_running
        )

    async def async_turn_on(self, **_: Any) -> None:
        await self.coordinator.async_set_sequencer_mode(SEQUENCER_MODE_SHUFFLE)

    async def async_turn_off(self, **_: Any) -> None:
        await self.coordinator.async_set_sequencer_mode(SEQUENCER_MODE_OFF)

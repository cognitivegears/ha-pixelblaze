"""Select platform — pattern picker, sequencer mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import (
    SEQUENCER_MODE_NAMES,
    SEQUENCER_MODE_OFF,
    SEQUENCER_NAME_TO_MODE,
)
from .entity import PixelblazeEntity

if TYPE_CHECKING:
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
    async_add_entities(
        [
            PixelblazePatternSelect(coordinator),
            PixelblazeSequencerModeSelect(coordinator),
        ]
    )


class PixelblazePatternSelect(PixelblazeEntity, SelectEntity):
    """Picks the active pattern by disambiguated label."""

    _attr_translation_key = "pattern"
    _attr_icon = "mdi:palette"

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_pattern"

    @property
    def options(self) -> list[str]:
        state = self.coordinator.data
        if not state:
            return []
        return sorted(state.pattern_label_to_id.keys())

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.data
        if not state or not state.active_pattern_id:
            return None
        for label, pid in state.pattern_label_to_id.items():
            if pid == state.active_pattern_id:
                return label
        return state.active_pattern_name

    async def async_select_option(self, option: str) -> None:
        state = self.coordinator.data
        if not state:
            return
        pid = state.find_pattern_id(option)
        if pid is not None:
            await self.coordinator.async_set_pattern(pid)


class PixelblazeSequencerModeSelect(PixelblazeEntity, SelectEntity):
    """Selects sequencer mode (off / shuffle / playlist)."""

    _attr_translation_key = "sequencer_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:playlist-play"
    _attr_options = list(SEQUENCER_NAME_TO_MODE.keys())

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_sequencer_mode"

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.data
        if not state:
            return None
        return SEQUENCER_MODE_NAMES.get(
            state.sequencer_mode, SEQUENCER_MODE_NAMES[SEQUENCER_MODE_OFF]
        )

    async def async_select_option(self, option: str) -> None:
        mode = SEQUENCER_NAME_TO_MODE.get(option, SEQUENCER_MODE_OFF)
        await self.coordinator.async_set_sequencer_mode(mode)

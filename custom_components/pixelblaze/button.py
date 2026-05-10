"""Button platform — next pattern, reboot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .api import PixelblazeError
from .entity import PixelblazeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PixelblazeConfigEntry
    from .coordinator import PixelblazeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

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
            PixelblazeNextPatternButton(coordinator),
            PixelblazeRebootButton(coordinator),
        ]
    )


class PixelblazeNextPatternButton(PixelblazeEntity, ButtonEntity):
    _attr_translation_key = "next_pattern"
    _attr_icon = "mdi:skip-next"

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_next_pattern"

    async def async_press(self) -> None:
        await self.coordinator.async_next_pattern()


class PixelblazeRebootButton(PixelblazeEntity, ButtonEntity):
    _attr_translation_key = "reboot"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_reboot"

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_reboot()
        except PixelblazeError as exc:
            raise HomeAssistantError(f"Reboot failed: {exc}") from exc

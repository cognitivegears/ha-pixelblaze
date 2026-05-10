"""Update platform — surfaces the device's installed firmware version.

We expose the *installed* version only. Detecting that an update is available
requires comparing against an upstream version source (ElectroMage's update
server) which is not yet wired in. Until that's implemented, ``latest_version``
mirrors ``installed_version`` so HA renders the entity as up-to-date and never
shows a misleading install prompt.

When upstream version detection is added, this entity should gain the
``INSTALL`` feature, and the coordinator should expose a wrapper that calls
the upstream library's ``installUpdate()`` method (currently absent — the
plumbing was deleted to avoid documenting a method-name landmine).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import PixelblazeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PixelblazeConfigEntry
    from .coordinator import PixelblazeDataUpdateCoordinator

# Read-only platform; coordinator drives all updates.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixelblazeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([PixelblazeFirmwareUpdate(coordinator)])


class PixelblazeFirmwareUpdate(PixelblazeEntity, UpdateEntity):
    """Firmware update entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "firmware"

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_id}_firmware"

    @property
    def installed_version(self) -> str | None:
        state = self.coordinator.data
        return state.version if state and state.version else None

    @property
    def latest_version(self) -> str | None:
        # We don't yet have an upstream version check, so we mirror the
        # installed version. HA renders the entity as "up to date" and never
        # advertises a phantom update. When a real check is implemented,
        # add UpdateEntityFeature.INSTALL and an async_install handler.
        return self.installed_version

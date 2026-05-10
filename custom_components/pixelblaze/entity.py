"""Base entity for Pixelblaze platforms.

``device_info`` is computed dynamically from the latest coordinator state so
that firmware upgrades, device renames, and bootstrap races (where the first
poll arrives with an empty ``pixelblaze_id``) are reflected without requiring
HA restart.

Entity identity is pinned to ``entry.unique_id`` so all platforms agree on
the device identifier — including dynamically-added per-pattern number
entities created on later polls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL

if TYPE_CHECKING:
    from .coordinator import PixelblazeDataUpdateCoordinator


def _format_configuration_url(host: str) -> str:
    """Build a click-through URL for the device's web UI, IPv6-safe."""
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    # Quote any unusual characters; preserve IPv6 brackets.
    return f"http://{quote(host, safe='[]:.')}/"


class PixelblazeEntity(CoordinatorEntity["PixelblazeDataUpdateCoordinator"]):
    """Base class for all Pixelblaze entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PixelblazeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        # Pin device identifier from the entry's unique_id so all platforms —
        # including entities created on later polls — agree on identity, even
        # if the first poll didn't yet have ``pixelblaze_id``.
        entry = coordinator.config_entry
        state = coordinator.data
        device_id = (
            (state.pixelblaze_id if state and state.pixelblaze_id else None)
            or entry.unique_id
            or entry.entry_id
        )
        self._device_id = device_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info derived from current coordinator state."""
        coordinator = self.coordinator
        state = coordinator.data
        entry = coordinator.config_entry
        name = (state.name if state and state.name else None) or entry.title or "Pixelblaze"
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=name,
            sw_version=state.version if state and state.version else None,
            configuration_url=_format_configuration_url(coordinator.client.host),
        )

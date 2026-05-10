"""Sensor platform for Pixelblaze."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.helpers.entity import EntityCategory

from .api import PixelblazeState
from .entity import PixelblazeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PixelblazeConfigEntry
    from .coordinator import PixelblazeDataUpdateCoordinator

# Read-only platform; coordinator drives all updates.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PixelblazeSensorDescription(SensorEntityDescription):
    """Describes a Pixelblaze sensor and how to extract its value."""

    value_fn: Callable[[PixelblazeState], Any]


SENSORS: tuple[PixelblazeSensorDescription, ...] = (
    PixelblazeSensorDescription(
        key="fps",
        translation_key="fps",
        native_unit_of_measurement="fps",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda s: round(s.fps, 1) if s.fps else None,
    ),
    PixelblazeSensorDescription(
        key="uptime",
        translation_key="uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.uptime_ms // 1000 if s.uptime_ms else None,
    ),
    PixelblazeSensorDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.version or None,
    ),
    PixelblazeSensorDescription(
        key="storage_used",
        translation_key="storage_used",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        suggested_unit_of_measurement=UnitOfInformation.KILOBYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.storage_used or None,
    ),
    PixelblazeSensorDescription(
        key="storage_size",
        translation_key="storage_size",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        suggested_unit_of_measurement=UnitOfInformation.KILOBYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.storage_size or None,
    ),
    PixelblazeSensorDescription(
        key="led_count",
        translation_key="led_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.led_count or None,
    ),
    PixelblazeSensorDescription(
        key="ip",
        translation_key="ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.ip or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixelblazeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PixelblazeSensor(coordinator, desc) for desc in SENSORS)


class PixelblazeSensor(PixelblazeEntity, SensorEntity):
    """Generic sensor backed by a description's ``value_fn``."""

    entity_description: PixelblazeSensorDescription

    def __init__(
        self,
        coordinator: PixelblazeDataUpdateCoordinator,
        description: PixelblazeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        state = self.coordinator.data
        if state is None:
            return None
        return self.entity_description.value_fn(state)

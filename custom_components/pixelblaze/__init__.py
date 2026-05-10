"""The Pixelblaze integration for Home Assistant."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .api import PixelblazeClient, PixelblazeConnectionError
from .config_flow import _canonical_device_id
from .const import (
    CONF_DISABLE_BEACON,
    CONF_PIXELBLAZE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import PixelblazeDataUpdateCoordinator
from .discovery import async_get_beacon_listener
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.UPDATE,
]


@dataclass
class PixelblazeRuntimeData:
    """Per-entry runtime data."""

    client: PixelblazeClient
    coordinator: PixelblazeDataUpdateCoordinator
    # True iff this entry holds a beacon-listener refcount that needs releasing
    # on unload. See ``PixelblazeBeaconListener.async_acquire``.
    beacon_acquired: bool = False


type PixelblazeConfigEntry = ConfigEntry[PixelblazeRuntimeData]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the integration. The beacon listener starts on first entry setup."""
    return True


def _migrate_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Convert legacy unique_ids to the canonical ``pb:xxxxxxxx`` form.

    Entries created before 0.2.5 stored the raw ``pixelblazeId`` hex string as
    the entry unique_id, while UDP discovery emits ``pb:xxxxxxxx``. The
    mismatch caused configured devices to keep appearing under "Discovered".
    """
    canonical = _canonical_device_id(entry.unique_id) or _canonical_device_id(
        entry.data.get(CONF_PIXELBLAZE_ID)
    )
    if canonical and entry.unique_id != canonical:
        hass.config_entries.async_update_entry(entry, unique_id=canonical)


async def async_setup_entry(hass: HomeAssistant, entry: PixelblazeConfigEntry) -> bool:
    """Set up a Pixelblaze config entry.

    Resource invariant: any resource we create here must be cleaned up if the
    function fails after creation. We construct the client first and wrap the
    rest in try/except so a failure mid-setup never leaks an open websocket.
    """
    _migrate_unique_id(hass, entry)

    host = entry.data[CONF_HOST]
    client = PixelblazeClient(hass, host)

    beacon_listener = None
    beacon_acquire_called = False

    try:
        try:
            await client.async_connect()
        except PixelblazeConnectionError as exc:
            raise ConfigEntryNotReady(f"Cannot connect to Pixelblaze at {host}") from exc

        scan_interval_opt = entry.options.get(CONF_SCAN_INTERVAL)
        scan_interval: timedelta = (
            timedelta(seconds=int(scan_interval_opt))
            if scan_interval_opt is not None
            else DEFAULT_SCAN_INTERVAL
        )
        coordinator = PixelblazeDataUpdateCoordinator(
            hass, entry, client, scan_interval=scan_interval
        )
        await coordinator.async_config_entry_first_refresh()

        if not entry.options.get(CONF_DISABLE_BEACON, False):
            beacon_listener = await async_get_beacon_listener(hass)
            await beacon_listener.async_acquire()
            beacon_acquire_called = True

        entry.runtime_data = PixelblazeRuntimeData(
            client=client,
            coordinator=coordinator,
            beacon_acquired=beacon_acquire_called,
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        async_setup_services(hass)
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    except BaseException:
        if beacon_acquire_called and beacon_listener is not None:
            with contextlib.suppress(Exception):
                await beacon_listener.async_release()
        with contextlib.suppress(Exception):
            await client.async_close()
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PixelblazeConfigEntry) -> bool:
    """Unload a Pixelblaze config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and getattr(entry, "runtime_data", None) is not None:
        runtime = entry.runtime_data
        if runtime.beacon_acquired:
            with contextlib.suppress(Exception):
                listener = await async_get_beacon_listener(hass)
                await listener.async_release()
        await runtime.client.async_close()
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: PixelblazeConfigEntry) -> None:
    """Reload entry when options change.

    Short-circuits when the new options match what the running coordinator is
    already using, so a benign options-flow save (user clicked Submit without
    changing anything) doesn't tear down and rebuild every entity for ~1s of
    UI flicker.
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        new_scan = entry.options.get(CONF_SCAN_INTERVAL)
        new_scan_s = (
            int(new_scan) if new_scan is not None else int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        current_scan_s = (
            int(runtime.coordinator.update_interval.total_seconds())
            if runtime.coordinator.update_interval is not None
            else int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        new_disable_beacon = bool(entry.options.get(CONF_DISABLE_BEACON, False))
        # ``runtime.beacon_acquired`` is True iff acquire was called for this
        # entry — i.e., the user did NOT disable the beacon listener.
        current_disable_beacon = not runtime.beacon_acquired
        if new_scan_s == current_scan_s and new_disable_beacon == current_disable_beacon:
            return
    await hass.config_entries.async_reload(entry.entry_id)

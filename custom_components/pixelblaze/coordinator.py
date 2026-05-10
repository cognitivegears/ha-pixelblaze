"""DataUpdateCoordinator for the Pixelblaze integration."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    PixelblazeClient,
    PixelblazeConnectionError,
    PixelblazeState,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PATTERN_LIST_REFRESH_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class PixelblazeDataUpdateCoordinator(DataUpdateCoordinator[PixelblazeState]):
    """Polls a Pixelblaze device on a fixed interval."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PixelblazeClient,
        scan_interval: timedelta | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            # Use entry_id (opaque) instead of title (often the IP) so log
            # lines don't leak network info on UpdateFailed.
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=scan_interval or DEFAULT_SCAN_INTERVAL,
        )
        self.config_entry = entry
        self.client = client
        self._last_pattern_id: str | None = None
        self._last_pattern_list_refresh: float | None = None
        self._force_pattern_list_refresh: bool = False

    async def _async_update_data(self) -> PixelblazeState:
        """Fetch a state snapshot. Raise ``UpdateFailed`` on connection errors."""
        # Periodic pattern-list refresh (every 5 min) or if explicitly requested.
        now = time.monotonic()
        refresh_interval_s = PATTERN_LIST_REFRESH_INTERVAL.total_seconds()
        force_refresh = (
            self._force_pattern_list_refresh
            or self._last_pattern_list_refresh is None
            or (now - self._last_pattern_list_refresh) > refresh_interval_s
        )

        try:
            state = await self.client.async_fetch_state(
                self._last_pattern_id, force_pattern_list=force_refresh
            )
        except PixelblazeConnectionError as exc:
            raise UpdateFailed(f"Cannot reach Pixelblaze: {exc}") from exc

        if force_refresh:
            self._last_pattern_list_refresh = now
            self._force_pattern_list_refresh = False

        prev = self._last_pattern_id
        self._last_pattern_id = state.active_pattern_id
        if prev != state.active_pattern_id:
            _LOGGER.debug("Active pattern changed: %s -> %s", prev, state.active_pattern_id)

        return state

    # ---- Optimistic-update helpers ----------------------------------------

    def _patch_state(self, **fields: Any) -> None:
        """Apply an optimistic local update so the UI reflects the change immediately.

        Returns silently if the first refresh hasn't populated ``data`` yet
        (HA types ``coordinator.data`` non-None per the TypeVar but it's
        None until the first refresh). Skips the notify when every patched
        field already matches current state, to avoid waking every entity
        on no-op writes (a brightness slider re-set to its current value
        would otherwise fire ``_handle_coordinator_update`` for every entity).
        """
        if self.data is None:
            return
        if all(getattr(self.data, k) == v for k, v in fields.items()):
            return
        self.async_set_updated_data(replace(self.data, **fields))

    # ---- Convenience wrappers used by entities & services -----------------

    async def async_set_brightness(self, value: float) -> None:
        await self.client.async_set_brightness(value)
        self._patch_state(brightness=max(0.0, min(1.0, float(value))))

    async def async_set_pattern(self, pattern_id: str) -> None:
        await self.client.async_set_pattern(pattern_id)
        if self.data is not None:
            self._patch_state(
                active_pattern_id=pattern_id,
                active_pattern_name=self.data.pattern_list.get(pattern_id),
            )

    async def async_set_paused(self, paused: bool) -> None:
        await self.client.async_pause_renderer(paused)
        self._patch_state(paused=bool(paused))

    async def async_set_sequencer_mode(self, mode: int) -> None:
        await self.client.async_set_sequencer_mode(mode)
        self._patch_state(sequencer_mode=int(mode), sequencer_running=mode != 0)

    async def async_next_pattern(self) -> None:
        await self.client.async_next_sequencer()
        await self.async_request_refresh()

    async def async_set_active_control(self, name: str, value: float) -> None:
        await self.client.async_set_active_control(name, value)
        if self.data is not None:
            new_controls = dict(self.data.active_controls)
            new_controls[name] = float(value)
            self._patch_state(active_controls=new_controls)

    async def async_set_color_control(self, name: str, hsv: list[float]) -> None:
        await self.client.async_set_color_control(name, hsv)
        if self.data is not None:
            new_controls = dict(self.data.active_controls)
            new_controls[name] = list(hsv)
            self._patch_state(active_controls=new_controls)

    async def async_set_active_variables(self, values: dict[str, Any]) -> None:
        await self.client.async_set_active_variables(values)
        if self.data is not None:
            new_vars = dict(self.data.active_variables)
            new_vars.update(values)
            self._patch_state(active_variables=new_vars)

    async def async_run_playlist(self, playlist_id: str) -> None:
        await self.client.async_set_playlist(playlist_id)
        await self.async_request_refresh()

    async def async_activate_scene(
        self,
        *,
        pattern_id: str | None = None,
        brightness: float | None = None,
        variables: dict[str, Any] | None = None,
        sequencer_mode: int | None = None,
    ) -> None:
        """Apply pattern, variables, brightness, and sequencer mode in one call.

        Order matters: pattern first (the device clears variable state when
        switching patterns), variables next (so the new pattern boots with the
        intended values), then brightness, then sequencer mode last. A single
        optimistic state patch is emitted at the end so subscribers see one
        coherent transition rather than four intermediate flickers.
        """
        patches: dict[str, Any] = {}

        if pattern_id is not None:
            await self.client.async_set_pattern(pattern_id)
            patches["active_pattern_id"] = pattern_id
            if self.data is not None:
                patches["active_pattern_name"] = self.data.pattern_list.get(pattern_id)

        if variables:
            await self.client.async_set_active_variables(variables)
            if self.data is not None:
                merged = dict(self.data.active_variables)
                merged.update(variables)
                patches["active_variables"] = merged

        if brightness is not None:
            clamped = max(0.0, min(1.0, float(brightness)))
            await self.client.async_set_brightness(clamped)
            patches["brightness"] = clamped
            if self.data is not None and self.data.paused and clamped > 0:
                await self.client.async_pause_renderer(False)
                patches["paused"] = False

        if sequencer_mode is not None:
            await self.client.async_set_sequencer_mode(sequencer_mode)
            patches["sequencer_mode"] = int(sequencer_mode)
            patches["sequencer_running"] = sequencer_mode != 0

        if patches:
            self._patch_state(**patches)

    async def async_refresh_pattern_list(self) -> None:
        """Force a fresh pattern-list fetch on the next coordinator cycle.

        ``_force_pattern_list_refresh`` is the actual signal — the next
        ``_async_update_data`` will pass ``forceRefresh=True`` to upstream
        ``getPatternList``, bypassing the lib's 600s cache.
        """
        self._force_pattern_list_refresh = True
        await self.async_request_refresh()

    async def async_reboot(self) -> None:
        await self.client.async_reboot()

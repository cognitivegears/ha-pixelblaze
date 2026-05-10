"""Async wrapper around the synchronous ``pixelblaze-client`` library.

The upstream library (``pixelblaze-client``) is built on ``websocket-client``
and is fully synchronous. We wrap each call in
``hass.async_add_executor_job`` and serialize calls per-device using an
``asyncio.Lock`` to keep the websocket consistent. Every call is also wrapped
in ``asyncio.timeout`` to prevent a hung device from holding an executor
thread forever.

Only library methods that do **not** require ``mini-racer`` are used in this
module. Pattern source decompilation/upload (which requires V8) is
intentionally out of scope for v1.0 — see README.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Hard ceiling on a single websocket round-trip. The library's per-packet
# recv_timeout is 1s but loops forever waiting for the *expected* message,
# which is how a hung device pins an executor thread. The async wait_for
# below is the only reliable timeout boundary.
DEFAULT_OPERATION_TIMEOUT = 8.0
SOCKET_RECV_TIMEOUT = 2.0


class PixelblazeError(Exception):
    """Base error for the Pixelblaze integration."""


class PixelblazeConnectionError(PixelblazeError):
    """Raised when the websocket cannot be reached."""


class PixelblazeCommandError(PixelblazeError):
    """Raised when a command is rejected by the device."""


@dataclass
class PixelblazeState:
    """Snapshot of the device state polled by the coordinator."""

    pixelblaze_id: str = ""
    name: str = ""
    version: str = ""
    ip: str = ""
    led_count: int = 0

    brightness: float = 1.0  # 0.0..1.0 (Pixelblaze brightness slider)
    paused: bool = False  # renderer paused == effectively off
    active_pattern_id: str | None = None
    active_pattern_name: str | None = None

    pattern_list: dict[str, str] = field(default_factory=dict)  # id -> name
    pattern_label_to_id: dict[str, str] = field(default_factory=dict)  # display label -> id

    sequencer_mode: int = 0  # 0=off, 1=shuffle, 2=playlist
    sequencer_running: bool = False
    playlist_id: str = "_defaultplaylist_"
    playlist_position: int = 0
    playlist_items: list[dict[str, Any]] = field(default_factory=list)

    fps: float = 0.0
    uptime_ms: int = 0
    storage_used: int = 0
    storage_size: int = 0

    network_power_save: bool = False

    active_controls: dict[str, Any] = field(default_factory=dict)
    active_variables: dict[str, Any] = field(default_factory=dict)

    def find_pattern_id(self, name_or_id: str) -> str | None:
        """Resolve a pattern by id, label, or name. Returns the canonical id or None."""
        if not name_or_id:
            return None
        if name_or_id in self.pattern_list:
            return name_or_id
        if name_or_id in self.pattern_label_to_id:
            return self.pattern_label_to_id[name_or_id]
        for pid, pname in self.pattern_list.items():
            if pname == name_or_id:
                return pid
        return None


def _build_pattern_labels(pattern_list: dict[str, str]) -> dict[str, str]:
    """Build a label→id map that disambiguates duplicate pattern names.

    Names that appear once map to themselves. Names that collide get a
    short id-suffix appended: ``"Sparkles (KGksY)"``.
    """
    name_counts: dict[str, int] = {}
    for name in pattern_list.values():
        name_counts[name] = name_counts.get(name, 0) + 1
    labels: dict[str, str] = {}
    for pid, name in pattern_list.items():
        label = name if name_counts[name] == 1 else f"{name} ({pid[:6]})"
        labels[label] = pid
    return labels


def _translate_exceptions(exc: BaseException) -> PixelblazeError:
    """Map common ``pixelblaze-client`` / ``websocket-client`` exceptions.

    `pixelblaze-client` is a hard dependency, so `websocket` is always present.
    The local import keeps test-time module patching robust.
    """
    try:
        from websocket import WebSocketException

        ws_types: tuple[type[BaseException], ...] = (WebSocketException,)
    except ImportError:
        ws_types = ()

    name = type(exc).__name__
    if isinstance(exc, (*ws_types, OSError, TimeoutError, ConnectionError)):
        return PixelblazeConnectionError(str(exc) or name)
    return PixelblazeCommandError(str(exc) or name)


class _PixelblazeProto(Protocol):
    """Subset of ``pixelblaze.Pixelblaze`` this integration uses.

    Defining the surface as a Protocol gives mypy a typed interface for the
    upstream object — typos in method names are caught at type-check time
    rather than at runtime. The real ``pixelblaze.Pixelblaze`` class is a
    structural match (it has every method named here); ``FakePixelblaze`` in
    the test stub does as well.
    """

    ws: Any  # underlying websocket; we settimeout()/close() on it directly

    # Polled state aggregation.
    def getConfigSettings(self) -> dict[str, Any]: ...
    def getConfigSequencer(self) -> dict[str, Any]: ...
    def getStatistics(self) -> dict[str, Any]: ...
    def getActivePattern(self, configSequencer: dict[str, Any] | None = ...) -> str | None: ...
    def getPatternList(self, forceRefresh: bool = ...) -> dict[str, str]: ...
    def getActiveControls(self, configSequencer: dict[str, Any] | None = ...) -> dict[str, Any]: ...
    def getActiveVariables(self) -> dict[str, Any]: ...
    def getVersion(self) -> Any: ...  # upstream returns float; we stringify
    def getBrightnessSlider(self, configSettings: dict[str, Any] | None = ...) -> float | None: ...

    # Commands (all kw-only saveToFlash where applicable, matching upstream).
    def setBrightnessSlider(self, brightness: float, *, saveToFlash: bool = ...) -> None: ...
    def setActivePattern(self, patternId: str, *, saveToFlash: bool = ...) -> None: ...
    def pauseRenderer(self, doPause: bool) -> None: ...
    def setActiveControls(
        self, dictControls: dict[str, Any], *, saveToFlash: bool = ...
    ) -> None: ...
    def setColorControl(self, controlName: str, color: Any, saveToFlash: bool = ...) -> None: ...
    def setActiveVariables(self, dictVariables: dict[str, Any]) -> None: ...
    def nextSequencer(self, *, saveToFlash: bool = ...) -> None: ...
    def setSequencerMode(self, sequencerMode: int, *, saveToFlash: bool = ...) -> None: ...
    def playSequencer(self) -> None: ...
    def pauseSequencer(self) -> None: ...
    def reboot(self) -> None: ...
    def installUpdate(self) -> Any: ...


class PixelblazeClient:
    """Async wrapper around ``pixelblaze.Pixelblaze``."""

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self._hass = hass
        self._host = host
        self._lock = asyncio.Lock()
        self._pb: _PixelblazeProto | None = None
        self._closed = False
        self._operation_timeout = DEFAULT_OPERATION_TIMEOUT

    @property
    def host(self) -> str:
        return self._host

    async def async_connect(self) -> None:
        """Open the websocket. Idempotent."""
        if self._pb is not None:
            return
        try:
            async with asyncio.timeout(self._operation_timeout):
                self._pb = await self._hass.async_add_executor_job(self._sync_connect)
        except TimeoutError as exc:
            raise PixelblazeConnectionError("connect timed out") from exc
        except Exception as exc:
            raise _translate_exceptions(exc) from exc

    def _sync_connect(self) -> _PixelblazeProto:
        from pixelblaze import Pixelblaze  # type: ignore[attr-defined]

        pb = Pixelblaze(self._host, ignoreOpenFailure=True)
        # Cap per-packet wait so a half-hung device can't pin the executor
        # thread inside the library's ``wsReceive`` loop.
        ws = getattr(pb, "ws", None)
        if ws is not None:
            with contextlib.suppress(Exception):
                ws.settimeout(SOCKET_RECV_TIMEOUT)
        # The real Pixelblaze class is a structural match against
        # _PixelblazeProto; mypy sees it as Any due to the module override.
        return cast(_PixelblazeProto, pb)

    async def async_close(self) -> None:
        """Close the websocket. Idempotent. Safe to call from cleanup paths."""
        if self._pb is None or self._closed:
            self._closed = True
            return
        self._closed = True
        pb = self._pb
        self._pb = None
        try:
            async with asyncio.timeout(2.0):
                await self._hass.async_add_executor_job(self._sync_close, pb)
        except (TimeoutError, Exception) as exc:
            _LOGGER.debug("Error closing Pixelblaze connection: %s", exc)

    @staticmethod
    def _sync_close(pb: _PixelblazeProto) -> None:
        # The Pixelblaze class has no public ``close``; close the websocket
        # directly. ``ws`` may be None if connect failed.
        ws = pb.ws
        if ws is not None:
            with contextlib.suppress(Exception):
                ws.close()

    async def _force_reconnect(self) -> None:
        """Drop the current ws so the next call reconnects fresh."""
        pb = self._pb
        self._pb = None
        if pb is not None:
            await self._hass.async_add_executor_job(self._sync_close, pb)

    async def _run(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a sync method on the underlying ``Pixelblaze`` under the lock."""
        if self._pb is None:
            await self.async_connect()
        async with self._lock:
            try:
                async with asyncio.timeout(self._operation_timeout):
                    return await self._hass.async_add_executor_job(
                        self._invoke, fn_name, args, kwargs
                    )
            except TimeoutError as exc:
                # The websocket may be wedged; force a reconnect on next call.
                await self._force_reconnect()
                raise PixelblazeConnectionError(
                    f"{fn_name} timed out after {self._operation_timeout}s"
                ) from exc
            except AttributeError as exc:
                # The library is missing this method (older release).
                raise PixelblazeCommandError(
                    f"{fn_name} not supported by pixelblaze-client"
                ) from exc
            except Exception as exc:
                raise _translate_exceptions(exc) from exc

    def _invoke(self, fn_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        fn = getattr(self._pb, fn_name)
        return fn(*args, **kwargs)

    # ---- Polled state -----------------------------------------------------

    async def async_fetch_state(
        self, prev_pattern_id: str | None, *, force_pattern_list: bool = False
    ) -> PixelblazeState:
        """Pull a coherent snapshot of device state in a single lock window.

        We fetch the underlying ``getConfigSettings``, ``getConfigSequencer``,
        and ``getStatistics`` once, then pass them to dependent helpers via
        their ``configSettings=`` / ``configSequencer=`` / ``savedStatistics=``
        keyword arguments. This cuts the round-trip count from ~10/poll
        (the naive call pattern) to ~3.
        """
        if self._pb is None:
            await self.async_connect()
        async with self._lock:
            try:
                async with asyncio.timeout(self._operation_timeout):
                    return await self._hass.async_add_executor_job(
                        self._sync_fetch_state, prev_pattern_id, force_pattern_list
                    )
            except TimeoutError as exc:
                await self._force_reconnect()
                raise PixelblazeConnectionError("poll timed out") from exc
            except Exception as exc:
                raise _translate_exceptions(exc) from exc

    def _sync_fetch_state(
        self, prev_pattern_id: str | None, force_pattern_list: bool
    ) -> PixelblazeState:
        pb = self._pb
        assert pb is not None  # async_fetch_state guarantees this

        # Three round-trips; each helper below reuses the cached dict.
        cfg: dict[str, Any] = _safe_get(pb.getConfigSettings, {})
        seq: dict[str, Any] = _safe_get(pb.getConfigSequencer, {})
        stats: dict[str, Any] = _safe_get(pb.getStatistics, {})

        active_id: str | None = _safe_get(lambda: pb.getActivePattern(configSequencer=seq), None)

        # getPatternList is cached upstream (default 600s after lib construction).
        # Force a refresh only when explicitly requested (e.g., from the
        # ``pixelblaze.refresh_pattern_list`` service).
        pattern_list: dict[str, str] = _safe_get(
            lambda: pb.getPatternList(forceRefresh=force_pattern_list), {}
        )

        # Active controls / variables only meaningful while a pattern is active.
        controls: dict[str, Any] = {}
        variables: dict[str, Any] = {}
        if active_id:
            controls = _safe_get(lambda: pb.getActiveControls(configSequencer=seq), {})
            variables = _safe_get(pb.getActiveVariables, {})

        version = _safe_get(pb.getVersion, None)
        version_str = "" if version is None else str(version)

        brightness: float | None = _safe_get(
            lambda: pb.getBrightnessSlider(configSettings=cfg), None
        )
        if brightness is None:
            brightness = float(cfg.get("brightness", 1.0))

        active_name = pattern_list.get(active_id) if active_id else None
        playlist = seq.get("playlist") or {}

        return PixelblazeState(
            pixelblaze_id=str(cfg.get("pixelblaze_id") or cfg.get("pixelblazeId") or ""),
            name=str(cfg.get("name") or ""),
            version=version_str,
            ip=str(cfg.get("ip") or self._host),
            led_count=int(cfg.get("pixelCount") or cfg.get("ledCount") or 0),
            brightness=float(brightness or 0.0),
            paused=bool(cfg.get("paused", False)),
            active_pattern_id=active_id or None,
            active_pattern_name=active_name,
            pattern_list=dict(pattern_list),
            pattern_label_to_id=_build_pattern_labels(pattern_list),
            sequencer_mode=int(seq.get("sequencerMode", 0)),
            sequencer_running=bool(seq.get("runSequencer", False)),
            playlist_id=str(playlist.get("id", "_defaultplaylist_")),
            playlist_position=int(playlist.get("position", 0)),
            playlist_items=list(playlist.get("items") or []),
            fps=float(stats.get("fps") or 0.0),
            uptime_ms=int(stats.get("uptime") or 0),
            storage_used=int(stats.get("storageUsed") or 0),
            storage_size=int(stats.get("storageSize") or 0),
            network_power_save=bool(cfg.get("networkPowerSave", False)),
            active_controls=dict(controls),
            active_variables=dict(variables),
        )

    # ---- Commands ---------------------------------------------------------

    async def async_set_brightness(self, value: float, *, save: bool = False) -> None:
        await self._run("setBrightnessSlider", max(0.0, min(1.0, float(value))), saveToFlash=save)

    async def async_set_pattern(self, pattern_id: str, *, save: bool = False) -> None:
        await self._run("setActivePattern", pattern_id, saveToFlash=save)

    async def async_pause_renderer(self, paused: bool) -> None:
        await self._run("pauseRenderer", bool(paused))

    async def async_set_active_control(self, name: str, value: Any, *, save: bool = False) -> None:
        # Upstream API only exposes the plural ``setActiveControls``.
        await self._run("setActiveControls", {name: value}, saveToFlash=save)

    async def async_set_active_controls(
        self, values: dict[str, Any], *, save: bool = False
    ) -> None:
        await self._run("setActiveControls", dict(values), saveToFlash=save)

    async def async_set_color_control(
        self, name: str, color: list[float], *, save: bool = False
    ) -> None:
        await self._run("setColorControl", name, list(color), save)

    async def async_set_active_variables(self, values: dict[str, Any]) -> None:
        await self._run("setActiveVariables", dict(values))

    async def async_next_sequencer(self, *, save: bool = False) -> None:
        await self._run("nextSequencer", saveToFlash=save)

    async def async_set_sequencer_mode(self, mode: int, *, save: bool = False) -> None:
        if mode not in (0, 1, 2):
            raise PixelblazeCommandError(f"invalid sequencer mode: {mode}")
        await self._run("setSequencerMode", int(mode), saveToFlash=save)

    async def async_play_sequencer(self) -> None:
        await self._run("playSequencer")

    async def async_pause_sequencer(self) -> None:
        await self._run("pauseSequencer")

    async def async_set_playlist(self, playlist_id: str) -> None:
        """Switch the sequencer into playlist mode for the named playlist.

        v1 limitation: only the default playlist (``_defaultplaylist_``) is
        currently supported. Selecting a non-default playlist by id requires
        loading its contents from the device first; that path is not yet
        wired up. Raises ``PixelblazeCommandError`` if the user requests a
        non-default playlist so automations fail loudly rather than silently
        loading the wrong content.
        """
        if playlist_id and playlist_id != "_defaultplaylist_":
            raise PixelblazeCommandError(
                "Selecting a non-default playlist by id is not yet supported. "
                "Use the Pixelblaze web UI to set the active playlist."
            )
        await self.async_set_sequencer_mode(2)

    async def async_reboot(self) -> None:
        await self._run("reboot")


def _safe_get[T](getter: Callable[[], T], default: T) -> T:
    """Invoke a zero-arg callable; on any exception, return the default.

    The polling pipeline aggregates many independent reads. If one fails
    (transient firmware quirk, single dropped websocket frame, etc.), the rest
    should still succeed. Caller passes a bound method or ``lambda``: typing
    is preserved end-to-end and there is no string-based ``getattr`` lookup —
    method-name typos are now caught by mypy.
    """
    try:
        return getter()
    except Exception as exc:
        _LOGGER.debug("Pixelblaze read failed; using default: %s", exc)
        return default

"""Shared test fixtures and stubs for the Pixelblaze integration."""

from __future__ import annotations

from collections.abc import Generator
import sys
import threading
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    return


class FakePixelblaze:
    """In-process stand-in for ``pixelblaze.Pixelblaze``.

    Mirrors the upstream API surface that the integration uses, including
    keyword-only ``saveToFlash`` arguments and the lack of a ``close`` method.
    The ``ws`` attribute is exposed so the integration's close-via-ws.close()
    path is exercised.
    """

    instances: list[FakePixelblaze] = []
    state_overrides: dict[str, Any] = {}

    def __init__(
        self,
        ipAddress: str,
        ignoreOpenFailure: bool = True,
        **_: Any,
    ) -> None:
        self.ipAddress = ipAddress
        self.host = ipAddress
        FakePixelblaze.instances.append(self)
        self._brightness = 0.5
        self._paused = False
        self._active = "ptn-001"
        self._sequencer_mode = 0
        self._sequencer_running = False
        self.last_set_variables: dict[str, Any] | None = None
        self.last_set_controls: dict[str, Any] | None = None
        self.last_set_color_control: tuple[Any, ...] | None = None
        self.next_called = False
        self.rebooted = False
        self.cache_refresh: int | None = None
        self.last_force_refresh: bool = False

        self.ws = MagicMock()
        self.ws.settimeout = MagicMock()
        self.ws.close = MagicMock()

    # ---- Configuration ----
    def getConfigSettings(self) -> dict[str, Any]:
        return {
            "name": FakePixelblaze.state_overrides.get("name", "Test Pixelblaze"),
            "pixelblaze_id": FakePixelblaze.state_overrides.get("pixelblaze_id", "deadbeef"),
            "ip": self.ipAddress,
            "pixelCount": FakePixelblaze.state_overrides.get("pixelCount", 64),
            "brightness": self._brightness,
            "paused": self._paused,
            "networkPowerSave": False,
        }

    def getConfigSequencer(self) -> dict[str, Any]:
        return {
            "sequencerMode": self._sequencer_mode,
            "runSequencer": self._sequencer_running,
            "playlist": {"id": "_defaultplaylist_", "position": 0, "items": []},
        }

    def getStatistics(self) -> dict[str, Any]:
        return {
            "fps": FakePixelblaze.state_overrides.get("fps", 60.0),
            "uptime": FakePixelblaze.state_overrides.get("uptime", 12345678),
            "storageUsed": 1024,
            "storageSize": 4096,
        }

    def getVersion(self) -> str:
        return FakePixelblaze.state_overrides.get("version", "3.30")

    # ---- Patterns ----
    def getPatternList(self, forceRefresh: bool = False) -> dict[str, str]:
        self.last_force_refresh = forceRefresh
        return FakePixelblaze.state_overrides.get(
            "patternList",
            {"ptn-001": "Rainbow", "ptn-002": "Sparkles", "ptn-003": "Fire"},
        )

    def getActivePattern(self, configSequencer: dict | None = None) -> str:
        return self._active

    def setActivePattern(self, patternId: str, *, saveToFlash: bool = False) -> None:
        self._active = patternId

    def getActiveControls(self, configSequencer: dict | None = None) -> dict[str, Any]:
        return FakePixelblaze.state_overrides.get(
            "activeControls", {"sliderSpeed": 0.5, "sliderIntensity": 0.8}
        )

    def setActiveControls(
        self,
        dictControls: dict[str, Any],
        *,
        saveToFlash: bool = False,
    ) -> None:
        self.last_set_controls = dict(dictControls)

    def setColorControl(
        self,
        controlName: str,
        color: Any,
        saveToFlash: bool = False,
    ) -> None:
        self.last_set_color_control = (controlName, color, saveToFlash)

    def getActiveVariables(self) -> dict[str, Any]:
        return {"hue": 0.5}

    def setActiveVariables(self, dictVariables: dict[str, Any]) -> None:
        self.last_set_variables = dict(dictVariables)

    # ---- Brightness ----
    def getBrightnessSlider(self, configSettings: dict | None = None) -> float:
        return self._brightness

    def setBrightnessSlider(
        self,
        brightness: float,
        *,
        saveToFlash: bool = False,
    ) -> None:
        self._brightness = float(brightness)

    def pauseRenderer(self, doPause: bool) -> None:
        self._paused = bool(doPause)

    # ---- Sequencer ----
    def setSequencerMode(
        self,
        sequencerMode: int,
        *,
        saveToFlash: bool = False,
    ) -> None:
        self._sequencer_mode = int(sequencerMode)
        self._sequencer_running = sequencerMode != 0

    def nextSequencer(self, *, saveToFlash: bool = False) -> None:
        self.next_called = True

    def playSequencer(self) -> None:
        self._sequencer_running = True

    def pauseSequencer(self) -> None:
        self._sequencer_running = False

    def setCacheRefreshTime(self, seconds: int) -> None:
        self.cache_refresh = seconds

    def reboot(self) -> None:
        self.rebooted = True

    def installUpdate(self) -> int:
        self.installed_update = True
        return 1


@pytest.fixture(autouse=True)
def fake_pixelblaze_module() -> Generator[None]:
    """Install a fake ``pixelblaze`` module before any code imports it."""
    FakePixelblaze.instances.clear()
    FakePixelblaze.state_overrides = {}

    pixelblaze = types.ModuleType("pixelblaze")
    pixelblaze.Pixelblaze = FakePixelblaze  # type: ignore[attr-defined]
    pixelblaze.PixelblazeEnumerator = MagicMock  # type: ignore[attr-defined]

    sys.modules["pixelblaze"] = pixelblaze
    yield
    sys.modules.pop("pixelblaze", None)


@pytest.fixture(autouse=True)
def fake_reachable(monkeypatch: Any, request: Any) -> None:
    """Default the async TCP-reachability probe to True for unit tests.

    The real probe calls ``asyncio.open_connection`` and would fail against
    the synthetic 1.2.3.4 host that fixtures use. Integration tests opt out
    via the ``integration`` marker so they exercise the live probe.
    """
    if request.node.get_closest_marker("integration"):
        return

    async def _always_reachable(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(
        "custom_components.pixelblaze.api.async_is_reachable",
        _always_reachable,
    )


@pytest.fixture(autouse=True)
def avoid_safe_shutdown_thread(monkeypatch: Any, request: Any) -> None:
    """Prevent HA's safe-shutdown background thread in unit tests."""
    if request.node.get_closest_marker("integration"):
        return
    _orig_start = threading.Thread.start

    def _patched_start(self: Any, *args: Any, **kwargs: Any) -> Any:
        target_name = getattr(getattr(self, "_target", None), "__name__", None)
        if target_name == "_run_safe_shutdown_loop":
            return None
        return _orig_start(self, *args, **kwargs)

    monkeypatch.setattr(threading.Thread, "start", _patched_start, raising=True)


@pytest.fixture
async def setup_entry(hass: Any) -> Any:
    """Create a configured Pixelblaze entry and return the MockConfigEntry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.pixelblaze.const import (
        CONF_DISABLE_BEACON,
        CONF_PIXELBLAZE_ID,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Pixelblaze",
        unique_id="pb:deadbeef",
        data={"host": "1.2.3.4", CONF_PIXELBLAZE_ID: "pb:deadbeef"},
        options={CONF_DISABLE_BEACON: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def setup_entry_with_device(hass: Any, setup_entry: Any) -> Any:
    """Return ``(entry, device)`` — the configured entry and its device-registry entry."""
    from homeassistant.helpers import device_registry as dr

    device = next(
        d for d in dr.async_get(hass).devices.values() if setup_entry.entry_id in d.config_entries
    )
    return setup_entry, device

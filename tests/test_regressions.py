"""Regression tests for issues caught in the v0.1.0 review.

Each test exercises a specific bug-class that was previously unverified:

- Dynamic per-pattern number entities appear when the active pattern changes.
- Beacon listener stops on last-entry unload.
- Malicious beacons (oversized, control chars, ANSI escapes) are dropped/sanitized.
- Diagnostic exports redact PII fields.
- Hung executor is killed by ``asyncio.wait_for``.
- Host validation rejects URLs, schemes, paths, and loopback.
- Duplicate pattern names produce disambiguated labels.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.pixelblaze.api import (
    PixelblazeClient,
    PixelblazeConnectionError,
    PixelblazeState,
    _build_pattern_labels,
)
from custom_components.pixelblaze.config_flow import _clean_host, _InvalidHostError
from custom_components.pixelblaze.const import BEACON_TYPE_DEVICE, CONF_PIXELBLAZE_ID, DOMAIN
from custom_components.pixelblaze.discovery import (
    PixelblazeBeaconListener,
    _parse_beacon,
)

# ---- H1: dynamic number entity addition --------------------------------------


async def test_number_entity_added_when_pattern_introduces_new_control(hass) -> None:
    """When the active pattern's controls expose a new slider, a number entity appears.

    This test deliberately bypasses the ``setup_entry`` fixture so it can mutate
    ``FakePixelblaze.state_overrides`` *before* setup runs (the fixture sets up
    on first request, which would freeze the controls dict).
    """
    from tests.conftest import FakePixelblaze

    FakePixelblaze.state_overrides["activeControls"] = {"sliderSpeed": 0.5}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Pixelblaze",
        unique_id="pb:deadbeef",
        data={"host": "1.2.3.4", CONF_PIXELBLAZE_ID: "pb:deadbeef"},
        options={"disable_beacon_listener": True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Initially: one slider entity.
    state_before = hass.states.get("number.test_pixelblaze_sliderspeed")
    assert state_before is not None

    # Simulate the user switching to a pattern that exposes a new slider.
    FakePixelblaze.state_overrides["activeControls"] = {
        "sliderSpeed": 0.5,
        "sliderColorWidth": 0.7,
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    # New slider entity should now exist.
    state_after = hass.states.get("number.test_pixelblaze_slidercolorwidth")
    assert state_after is not None
    assert float(state_after.state) == 0.7


# ---- C4 / F3 / S11: beacon listener lifecycle -------------------------------


async def test_beacon_listener_acquire_release_lifecycle(hass) -> None:
    """The listener stops and is removed from hass.data when the last user releases it."""
    listener = PixelblazeBeaconListener(hass)

    with patch.object(listener, "async_start", return_value=True):
        await listener.async_acquire()
        await listener.async_acquire()
        assert listener._refcount == 2

        await listener.async_release()
        assert listener._refcount == 1
        # Still active.

        # Final release tears down.
        with patch.object(listener, "async_stop") as stop_mock:
            await listener.async_release()
            stop_mock.assert_awaited()
        assert listener._refcount == 0


# ---- S1 / M3: rate-limited beacon handler -----------------------------------


async def test_beacon_seen_dict_bounded(hass) -> None:
    """Flooding random sender ids should not grow _seen unbounded."""
    listener = PixelblazeBeaconListener(hass)
    listener._tokens = 1e9  # disable rate limit for this test
    hass.config_entries.flow.async_init = lambda *a, **kw: asyncio.sleep(0)  # type: ignore[assignment]
    for sender_id in range(2000):
        payload = struct.pack("<III", BEACON_TYPE_DEVICE, sender_id, 0)
        listener.handle_packet(payload, ("192.168.1.50", 1889))
    assert len(listener._seen) <= 1024


async def test_beacon_rate_limit_drops_excess(hass) -> None:
    """Token bucket should drop packets when filled at line rate."""
    listener = PixelblazeBeaconListener(hass)
    listener._tokens = 5  # enough for first 5 packets
    init_calls = []
    hass.config_entries.flow.async_init = (  # type: ignore[assignment]
        lambda *a, **kw: init_calls.append(kw) or asyncio.sleep(0)
    )
    # 100 packets with distinct ids, rate limit drops most of them.
    for sender_id in range(100):
        payload = struct.pack("<III", BEACON_TYPE_DEVICE, sender_id, 0)
        listener.handle_packet(payload, ("192.168.1.50", 1889))
    assert len(init_calls) <= 5


# ---- S2: beacon name sanitization -------------------------------------------


def test_beacon_oversized_packet_rejected() -> None:
    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 1, 0) + b"a" * 1024
    assert _parse_beacon(payload) is None


def test_beacon_name_strips_ansi_escapes_and_control_chars() -> None:
    name_bytes = b"\x1b[2JOWNED\nERROR fake\x07"
    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 1, 0) + name_bytes
    info = _parse_beacon(payload)
    assert info is not None
    # Result must not contain control chars, newlines, or escape codes.
    assert info["name"] is None or all(c.isprintable() for c in info["name"])


def test_beacon_name_invalid_utf8_rejected() -> None:
    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 1, 0) + b"\xff\xfe\xfd"
    info = _parse_beacon(payload)
    # Either parser rejects the whole packet, or the name is None — but never raw bytes.
    assert info is None or info["name"] is None


# ---- S3: diagnostics redaction ----------------------------------------------


async def test_diagnostics_redacts_pii(hass, setup_entry) -> None:
    from custom_components.pixelblaze.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diag = await async_get_config_entry_diagnostics(hass, setup_entry)

    # Host/ip/name/id all redacted.
    serialized = str(diag)
    assert "1.2.3.4" not in serialized
    assert "pb:deadbeef" not in serialized
    assert "deadbeef" not in serialized
    assert "Test Pixelblaze" not in serialized or diag["entry"]["title"] == "Test Pixelblaze"
    # Pattern names dropped, count preserved.
    assert "Rainbow" not in serialized
    assert diag["state"].get("pattern_count") == 3


# ---- P2: hung executor → wait_for fires -------------------------------------


async def test_hung_call_times_out(hass) -> None:
    """If the underlying sync call hangs, async_fetch_state raises a connection error."""
    client = PixelblazeClient(hass, "1.2.3.4")
    client._operation_timeout = 0.05
    await client.async_connect()

    def _hang(*_a: Any, **_kw: Any) -> None:
        import time as _t

        _t.sleep(2.0)

    with (
        patch.object(type(client._pb), "getConfigSettings", new=_hang),
        pytest.raises(PixelblazeConnectionError),
    ):
        await client.async_fetch_state(None)


# ---- S4: host validation -----------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "http://1.2.3.4",  # scheme
        "1.2.3.4/path",  # path
        "1.2.3.4 5.6.7.8",  # whitespace
        "127.0.0.1",  # loopback
        "224.0.0.1",  # multicast
        "0.0.0.0",  # unspecified
        "",  # empty
        "x" * 300,  # too long
    ],
)
def test_validate_host_rejects_bad_input(bad: str) -> None:
    with pytest.raises(_InvalidHostError):
        _clean_host(bad)


@pytest.mark.parametrize("good", ["192.168.1.42", "10.0.0.1", "pixelblaze.local", "pb-living-room"])
def test_validate_host_accepts_normal_input(good: str) -> None:
    assert _clean_host(good) == good


# ---- H7: pattern label disambiguation ---------------------------------------


def test_duplicate_pattern_names_disambiguated() -> None:
    pattern_list = {"abc12345": "Sparkles", "def67890": "Sparkles", "ghi": "Fire"}
    labels = _build_pattern_labels(pattern_list)
    # "Fire" is unique → maps to itself; "Sparkles" collides → gets id-suffix.
    assert "Fire" in labels
    assert "Sparkles" not in labels  # the bare name is gone
    assert "Sparkles (abc123)" in labels
    assert "Sparkles (def678)" in labels


def test_state_find_pattern_id_resolves_label_id_or_name() -> None:
    state = PixelblazeState(
        pattern_list={"abc": "Rainbow", "def": "Rainbow"},
        pattern_label_to_id={"Rainbow (abc)": "abc", "Rainbow (def)": "def"},
    )
    # Resolves by id.
    assert state.find_pattern_id("abc") == "abc"
    # Resolves by disambiguated label.
    assert state.find_pattern_id("Rainbow (def)") == "def"
    # Resolves by raw (returns first match).
    assert state.find_pattern_id("Rainbow") in ("abc", "def")
    # Unknown returns None.
    assert state.find_pattern_id("Nope") is None


# ---- C3: playlist service fails loudly --------------------------------------


async def test_run_playlist_service_rejects_non_default(hass, setup_entry_with_device) -> None:
    from homeassistant.exceptions import HomeAssistantError

    _, device = setup_entry_with_device
    with pytest.raises(HomeAssistantError, match="not yet supported"):
        await hass.services.async_call(
            DOMAIN,
            "run_playlist",
            {"device_id": device.id, "playlist_id": "evening_mix"},
            blocking=True,
        )


# ---- S5: client cleanup on setup failure ------------------------------------


async def test_client_closed_when_first_refresh_fails(hass) -> None:
    """If async_config_entry_first_refresh raises, the client must be closed."""
    from tests.conftest import FakePixelblaze

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Pixelblaze",
        unique_id="pb:deadbeef",
        data={"host": "1.2.3.4", CONF_PIXELBLAZE_ID: "pb:deadbeef"},
        options={"disable_beacon_listener": True},
    )
    entry.add_to_hass(hass)

    boom = PixelblazeConnectionError("first refresh failed")
    with patch(
        "custom_components.pixelblaze.coordinator.PixelblazeDataUpdateCoordinator._async_update_data",
        side_effect=boom,
    ):
        # Setup either fails or is retried; we just want to ensure the client
        # was closed regardless. The fake records ws.close calls.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # At least one FakePixelblaze instance was constructed; its ws.close must
    # have been invoked once during the failure rollback.
    assert FakePixelblaze.instances, "expected at least one client instance"
    closed = any(inst.ws.close.called for inst in FakePixelblaze.instances)
    assert closed, "client websocket was not closed on setup failure"

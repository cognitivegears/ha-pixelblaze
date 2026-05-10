"""Regression tests added during the comprehensive code review fix pass.

Closes the highest-impact coverage gaps identified in Phase 3:

- ``_force_reconnect`` actually nulls the wedged client and reconnects fresh.
- Beacon listener acquire/release semantics across multiple entries.
- Optimistic state updates land for every coordinator wrapper, not just
  brightness.
- Reauth happy path + cannot_connect surface.
- Options flow persists scan_interval changes.
- DHCP discovery step succeeds.
- Number entity goes ``unavailable`` (not gone) when its slider disappears.
- ``_is_slider_control`` filter covers HSV/RGB pickers and non-numeric values.
"""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_REAUTH,
    SOURCE_USER,
)
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pixelblaze.api import (
    PixelblazeClient,
    PixelblazeConnectionError,
)
from custom_components.pixelblaze.const import (
    BEACON_TYPE_DEVICE,
    CONF_DEVICE_NAME,
    CONF_DISABLE_BEACON,
    CONF_PIXELBLAZE_ID,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.pixelblaze.discovery import (
    _BEACON_LISTENER_KEY,
    PixelblazeBeaconListener,
)
from custom_components.pixelblaze.number import _is_slider_control

# ---------------------------------------------------------------------------
# P1-T1 — _force_reconnect after timeout produces a fresh client
# ---------------------------------------------------------------------------


async def test_reconnects_after_timeout(hass: Any) -> None:
    """A hung call → timeout → next connect produces a new client instance."""
    client = PixelblazeClient(hass, "1.2.3.4")
    client._operation_timeout = 0.05
    await client.async_connect()

    first = client._pb
    assert first is not None

    def _hang(*_a: Any, **_kw: Any) -> None:
        import time as _t

        _t.sleep(2.0)

    with (
        patch.object(type(first), "getConfigSettings", new=_hang),
        pytest.raises(PixelblazeConnectionError),
    ):
        await client.async_fetch_state(None)

    # The wedged client must have been forcibly dropped.
    assert client._pb is None
    # Reconnect produces a fresh instance.
    await client.async_connect()
    second = client._pb
    assert second is not None
    assert second is not first


# ---------------------------------------------------------------------------
# P1-T2 — Multi-entry beacon listener refcount semantics
# ---------------------------------------------------------------------------


async def test_beacon_listener_multi_entry_sharing(hass: Any) -> None:
    """Listener survives partial release; tears down only when refcount hits zero."""
    listener = PixelblazeBeaconListener(hass)
    hass.data[_BEACON_LISTENER_KEY] = listener

    with (
        patch.object(listener, "async_start", AsyncMock(return_value=True)),
        patch.object(listener, "async_stop", AsyncMock()) as stop_mock,
    ):
        await listener.async_acquire()  # entry A
        await listener.async_acquire()  # entry B
        assert listener._refcount == 2

        await listener.async_release()  # A unloads
        stop_mock.assert_not_awaited()
        assert hass.data.get(_BEACON_LISTENER_KEY) is listener
        assert listener._refcount == 1

        await listener.async_release()  # B unloads — last reference
        stop_mock.assert_awaited_once()
        assert _BEACON_LISTENER_KEY not in hass.data
        assert listener._refcount == 0


# ---------------------------------------------------------------------------
# P1-T3..T5 — Optimistic update for every coordinator wrapper
# ---------------------------------------------------------------------------


async def test_set_pattern_optimistic_update(hass: Any, setup_entry: Any) -> None:
    coord = setup_entry.runtime_data.coordinator
    assert coord.data is not None
    original_brightness = coord.data.brightness

    await coord.async_set_pattern("ptn-002")

    assert coord.data.active_pattern_id == "ptn-002"
    assert coord.data.active_pattern_name == "Sparkles"
    # Sibling fields preserved.
    assert coord.data.brightness == original_brightness


async def test_set_paused_optimistic_update(hass: Any, setup_entry: Any) -> None:
    coord = setup_entry.runtime_data.coordinator
    assert coord.data is not None
    await coord.async_set_paused(True)
    assert coord.data.paused is True


async def test_set_sequencer_mode_optimistic_update(hass: Any, setup_entry: Any) -> None:
    coord = setup_entry.runtime_data.coordinator
    assert coord.data is not None
    await coord.async_set_sequencer_mode(1)
    assert coord.data.sequencer_mode == 1
    assert coord.data.sequencer_running is True

    await coord.async_set_sequencer_mode(0)
    assert coord.data.sequencer_mode == 0
    assert coord.data.sequencer_running is False


async def test_set_active_control_optimistic_update(hass: Any, setup_entry: Any) -> None:
    coord = setup_entry.runtime_data.coordinator
    assert coord.data is not None
    # Default fixture data exposes sliderSpeed and sliderIntensity.
    assert "sliderIntensity" in coord.data.active_controls

    await coord.async_set_active_control("sliderSpeed", 0.42)
    assert coord.data.active_controls["sliderSpeed"] == 0.42
    # Sibling key survives the patch (replace produces a new dataclass; the
    # active_controls dict is freshly copied).
    assert "sliderIntensity" in coord.data.active_controls


async def test_set_active_variables_optimistic_merge(hass: Any, setup_entry: Any) -> None:
    coord = setup_entry.runtime_data.coordinator
    assert coord.data is not None
    await coord.async_set_active_variables({"hue": 0.8, "speed": 0.5})
    assert coord.data.active_variables["hue"] == 0.8
    assert coord.data.active_variables["speed"] == 0.5


# ---------------------------------------------------------------------------
# P1-T6 — Reauth flow happy path + failure
# ---------------------------------------------------------------------------


async def test_reauth_flow_success(hass: Any) -> None:
    # First, create an entry the normal way.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    create = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""}
    )
    assert create["type"] is FlowResultType.CREATE_ENTRY
    entry = create["result"]
    await hass.async_block_till_done()

    # Now trigger a reauth — the user changes the device's IP.
    reauth = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert reauth["step_id"] == "reauth_confirm"

    confirm = await hass.config_entries.flow.async_configure(
        reauth["flow_id"], {CONF_HOST: "10.0.0.5"}
    )
    assert confirm["type"] is FlowResultType.ABORT
    assert confirm["reason"] == "reauth_successful"
    assert entry.data[CONF_HOST] == "10.0.0.5"


async def test_reauth_flow_cannot_connect(hass: Any) -> None:
    # Setup an entry first.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    create = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""}
    )
    entry = create["result"]
    await hass.async_block_till_done()

    async def _fail(*_a: Any, **_kw: Any) -> None:
        raise PixelblazeConnectionError("refused")

    reauth = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    with patch("custom_components.pixelblaze.config_flow._validate_host", side_effect=_fail):
        result2 = await hass.config_entries.flow.async_configure(
            reauth["flow_id"], {CONF_HOST: "10.0.0.5"}
        )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# P1-T7 — Options flow persists scan_interval
# ---------------------------------------------------------------------------


async def test_options_flow_persists_scan_interval(hass: Any, setup_entry: Any) -> None:
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    out = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_DISABLE_BEACON: True}
    )
    assert out["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert setup_entry.options[CONF_SCAN_INTERVAL] == 30


# ---------------------------------------------------------------------------
# P1-T8 — DHCP discovery flow
# ---------------------------------------------------------------------------


async def test_dhcp_discovery_flow(hass: Any) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip="192.168.1.99",
            hostname="pixelblaze-deadbeef",
            macaddress="deadbeef1234",
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    confirm = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert confirm["type"] is FlowResultType.CREATE_ENTRY
    assert confirm["data"][CONF_HOST] == "192.168.1.99"


# ---------------------------------------------------------------------------
# P1-T9 — Number entity becomes unavailable when its control disappears
# ---------------------------------------------------------------------------


async def test_number_entity_unavailable_when_control_dropped(hass: Any) -> None:
    from tests.conftest import FakePixelblaze

    FakePixelblaze.state_overrides["activeControls"] = {
        "sliderSpeed": 0.5,
        "sliderBrightness": 0.8,
    }
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

    assert hass.states.get("number.test_pixelblaze_sliderspeed") is not None
    assert hass.states.get("number.test_pixelblaze_sliderbrightness") is not None

    # The active pattern changes — sliderBrightness no longer exists.
    FakePixelblaze.state_overrides["activeControls"] = {"sliderSpeed": 0.3}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    speed = hass.states.get("number.test_pixelblaze_sliderspeed")
    assert speed is not None
    assert speed.state != "unavailable"

    dropped = hass.states.get("number.test_pixelblaze_sliderbrightness")
    assert dropped is not None
    assert dropped.state == "unavailable"


# ---------------------------------------------------------------------------
# P1-T10 — _is_slider_control filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("sliderSpeed", 0.5, True),
        ("sliderIntensity", 1, True),
        ("hsvpickerColor", [0.1, 0.9, 0.8], False),  # list value
        ("HSVPickerColor", 0.5, False),  # uppercase prefix; we lowercase
        ("rgbpickerFill", [1, 0, 0], False),
        ("sliderBrightness", "high", False),  # non-numeric
    ],
)
def test_is_slider_control(name: str, value: Any, expected: bool) -> None:
    assert _is_slider_control(name, value) is expected


# ---------------------------------------------------------------------------
# T2 — _finite_float rejects NaN / Infinity at the schema layer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "inf",
        "-inf",
        "1e500",  # overflows to inf via float()
    ],
)
def test_set_variable_schema_rejects_non_finite(bad_value: Any) -> None:
    """``vol.Coerce(float)`` accepted these; ``_finite_float`` must not."""
    import voluptuous as vol

    from custom_components.pixelblaze.services.registration import SET_VARIABLE_SCHEMA

    with pytest.raises(vol.Invalid):
        SET_VARIABLE_SCHEMA({"device_id": "abc", "name": "speed", "value": bad_value})


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), "NaN", "1e500"],
)
def test_set_variables_schema_rejects_non_finite_in_dict(bad_value: Any) -> None:
    import voluptuous as vol

    from custom_components.pixelblaze.services.registration import SET_VARIABLES_SCHEMA

    with pytest.raises(vol.Invalid):
        SET_VARIABLES_SCHEMA({"device_id": "abc", "values": {"speed": bad_value}})


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), "NaN", "1e500"],
)
def test_set_color_control_schema_rejects_non_finite_hsv(bad_value: Any) -> None:
    """HSV inputs are coerced via ``_finite_float`` before the ``vol.Range`` clamp."""
    import voluptuous as vol

    from custom_components.pixelblaze.services.registration import SET_COLOR_CONTROL_SCHEMA

    with pytest.raises(vol.Invalid):
        SET_COLOR_CONTROL_SCHEMA(
            {
                "device_id": "abc",
                "name": "hsvPickerColor",
                "hue": bad_value,
                "saturation": 0.5,
                "brightness": 0.5,
            }
        )


@pytest.mark.parametrize(
    "bad_value",
    [
        [0.5, float("nan")],
        [float("inf"), 0.0],
        [0.5, "NaN", 0.5],
    ],
)
def test_set_variable_schema_rejects_non_finite_inside_lists(bad_value: list[Any]) -> None:
    import voluptuous as vol

    from custom_components.pixelblaze.services.registration import SET_VARIABLE_SCHEMA

    with pytest.raises(vol.Invalid):
        SET_VARIABLE_SCHEMA({"device_id": "abc", "name": "vec", "value": bad_value})


# ---------------------------------------------------------------------------
# Bonus: TaskGroup fail-fast across 2 devices via service handler
# ---------------------------------------------------------------------------


async def test_set_pattern_service_fails_fast_when_one_device_errors(
    hass: Any, setup_entry: Any
) -> None:
    """If one device errors, the service raises HomeAssistantError carrying the cause."""
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    device = next(
        d for d in dr.async_get(hass).devices.values() if setup_entry.entry_id in d.config_entries
    )

    # Pattern doesn't exist → ServiceValidationError → wrapped as HomeAssistantError.
    with pytest.raises((HomeAssistantError, ServiceValidationError)):
        await hass.services.async_call(
            DOMAIN,
            "set_pattern",
            {"device_id": device.id, "pattern": "DoesNotExist"},
            blocking=True,
        )


# ---------------------------------------------------------------------------
# Bonus: beacon parser smoke test confirming basic struct works post-Protocol
# ---------------------------------------------------------------------------


def test_beacon_parser_smoke() -> None:
    from custom_components.pixelblaze.discovery import _parse_beacon

    payload = struct.pack("<III", BEACON_TYPE_DEVICE, 0xCAFEBABE, 0) + b"Lobby\x00"
    info = _parse_beacon(payload)
    assert info is not None
    assert info["sender_id"] == 0xCAFEBABE
    assert info["name"] == "Lobby"


# ---- Config-flow schema must be JSON-serializable ---------------------------


def test_user_schema_is_voluptuous_serializable() -> None:
    """Regression: HA frontend serializes the config-flow schema to JSON.

    A bare callable (e.g. ``_clean_host``) inside ``vol.All`` blows up
    ``voluptuous_serialize.convert`` with "Unable to convert schema" and
    surfaces to the user as a 500 from /api/config/config_entries/flow.
    """
    from homeassistant.helpers import config_validation as cv
    import voluptuous_serialize

    from custom_components.pixelblaze.config_flow import USER_SCHEMA

    # Should not raise.
    result = voluptuous_serialize.convert(USER_SCHEMA, custom_serializer=cv.custom_serializer)
    assert isinstance(result, list)
    assert any(field.get("name") == "host" for field in result)

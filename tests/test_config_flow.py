"""Tests for the Pixelblaze config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pixelblaze.const import (
    CONF_DEVICE_NAME,
    CONF_PIXELBLAZE_ID,
    DOMAIN,
)


async def test_user_flow_success(hass) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""},
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_HOST] == "1.2.3.4"
    assert result2["data"][CONF_PIXELBLAZE_ID] == "pb:deadbeef"
    assert result2["title"] == "Test Pixelblaze"


async def test_user_flow_cannot_connect(hass) -> None:
    from custom_components.pixelblaze.api import PixelblazeConnectionError

    async def _fail(*_, **__):
        raise PixelblazeConnectionError("nope")

    with patch("custom_components.pixelblaze.config_flow._validate_host", side_effect=_fail):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""},
        )
        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_duplicate_entry_aborts(hass) -> None:
    """Adding the same Pixelblaze twice aborts."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""},
    )

    result2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_HOST: "1.2.3.5", CONF_DEVICE_NAME: ""},
    )
    assert result3["type"] is FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


async def test_integration_discovery_flow(hass) -> None:
    """A beacon discovery initiates a confirm step that creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "integration_discovery"},
        data={"host": "1.2.3.4", "id": "pb:deadbeef", "name": "Lobby Strip"},
    )
    # Either the confirm form or an immediate entry creation depending on HA version.
    assert result["type"] in (FlowResultType.FORM, FlowResultType.CREATE_ENTRY)
    if result["type"] is FlowResultType.FORM:
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result2["type"] is FlowResultType.CREATE_ENTRY
        assert result2["data"][CONF_HOST] == "1.2.3.4"


async def test_discovery_aborts_for_user_configured_entry(hass) -> None:
    """A user-flow entry must dedup against subsequent UDP-beacon discovery.

    Regression: pre-0.2.5 the user flow stored the raw hex ``pixelblazeId`` as
    the entry unique_id while UDP discovery emitted ``pb:xxxxxxxx``. The
    mismatch made already-configured devices reappear under "Discovered".
    """
    # Set up via user flow first.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    created = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.2.3.4", CONF_DEVICE_NAME: ""},
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY

    # Now a beacon arrives for the same device — should abort.
    discovery = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "integration_discovery"},
        data={"host": "1.2.3.4", "id": "pb:deadbeef", "name": "Lobby Strip"},
    )
    assert discovery["type"] is FlowResultType.ABORT
    assert discovery["reason"] == "already_configured"


async def test_discovery_heals_legacy_host_unique_id(hass) -> None:
    """Entries from very old versions stored the host as unique_id.

    The startup migration can't canonicalize a non-hex unique_id, so the
    discovery flow has a fallback: if any existing entry's host or stored
    pixelblaze_id matches the discovered device, abort and rewrite the
    entry's unique_id to the canonical form. Without this fallback, a
    device whose original setup pre-dated `pixelblaze_id` propagation
    would keep reappearing under "Discovered" forever.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # Simulate a legacy entry: unique_id is the host, pixelblaze_id was never
    # populated correctly, so it also stores the host.
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pixelblaze",
        unique_id="192.168.1.160",
        data={CONF_HOST: "192.168.1.160", CONF_PIXELBLAZE_ID: "192.168.1.160"},
    )
    entry.add_to_hass(hass)

    discovery = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "integration_discovery"},
        data={"host": "192.168.1.160", "id": "pb:0064c4ee", "name": "Lobby Strip"},
    )
    assert discovery["type"] is FlowResultType.ABORT
    assert discovery["reason"] == "already_configured"
    # Entry should have been healed to the canonical form.
    assert entry.unique_id == "pb:0064c4ee"
    assert entry.data[CONF_PIXELBLAZE_ID] == "pb:0064c4ee"


async def test_canonical_device_id_normalizes_legacy_formats() -> None:
    from custom_components.pixelblaze.config_flow import _canonical_device_id

    assert _canonical_device_id("deadbeef") == "pb:deadbeef"
    assert _canonical_device_id("DEADBEEF") == "pb:deadbeef"
    assert _canonical_device_id("pb:deadbeef") == "pb:deadbeef"
    assert _canonical_device_id(0xDEADBEEF) == "pb:deadbeef"
    # Short hex gets zero-padded to 8 chars.
    assert _canonical_device_id("abc") == "pb:00000abc"
    # Non-hex / empty returns None so callers fall back to host.
    assert _canonical_device_id("not-hex") is None
    assert _canonical_device_id("") is None
    assert _canonical_device_id(None) is None

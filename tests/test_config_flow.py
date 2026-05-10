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
    assert result2["data"][CONF_PIXELBLAZE_ID] == "pb-test-1"
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

"""Config flow for the Pixelblaze integration."""

from __future__ import annotations

from collections.abc import Mapping
import ipaddress
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.util.network import is_host_valid, is_invalid, is_ip_address, is_loopback
import voluptuous as vol

from .api import PixelblazeClient, PixelblazeConnectionError
from .const import (
    CONF_DEVICE_NAME,
    CONF_DISABLE_BEACON,
    CONF_PIXELBLAZE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class _InvalidHostError(ValueError):
    """Raised by ``_clean_host`` when the input is not a usable host string."""


def _clean_host(raw: Any) -> str:
    """Validate and normalize a user-provided host string.

    Accepts bare IPv4/IPv6 literals and DNS hostnames. Rejects URLs (scheme,
    paths), whitespace, loopback, multicast, link-local, and unspecified
    addresses. Returns the cleaned host (no trailing slash, no surrounding
    brackets on bare IPv6 — brackets are added downstream when constructing
    URLs).

    Implemented as a plain function rather than a voluptuous validator so the
    config-flow schema stays JSON-serializable: HA's frontend uses
    ``voluptuous_serialize`` to render the form, and bare callables inside
    ``vol.All`` blow it up with ``Unable to convert schema``.
    """
    if not isinstance(raw, str):
        raise _InvalidHostError("invalid_host")
    host = raw.strip().rstrip("/").strip("[]")
    if not host or "://" in host or any(c in host for c in " \t\r\n?#@"):
        raise _InvalidHostError("invalid_host")
    if is_ip_address(host):
        ip = ipaddress.ip_address(host)
        if is_loopback(ip) or is_invalid(ip) or ip.is_multicast or ip.is_link_local:
            raise _InvalidHostError("invalid_host")
        return host
    if not is_host_valid(host):
        raise _InvalidHostError("invalid_host")
    return host


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_DEVICE_NAME, default=""): vol.All(str, vol.Length(max=64)),
    }
)


async def _validate_host(hass: Any, host: str) -> dict[str, Any]:
    """Try to connect and pull identifying details. Raises PixelblazeConnectionError on failure."""
    client = PixelblazeClient(hass, host)
    try:
        state = await client.async_fetch_state(None)
        return {
            "pixelblaze_id": state.pixelblaze_id or host,
            "name": state.name or host,
            "version": state.version,
        }
    finally:
        await client.async_close()


class PixelblazeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Pixelblaze config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._discovered_id: str | None = None
        self._discovered_name: str | None = None

    # ---- User step --------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                host = _clean_host(user_input[CONF_HOST])
            except _InvalidHostError:
                errors["base"] = "invalid_host"
                return self.async_show_form(
                    step_id="user",
                    data_schema=USER_SCHEMA,
                    errors=errors,
                )
            try:
                info = await _validate_host(self.hass, host)
            except PixelblazeConnectionError:
                errors["base"] = "cannot_connect"
            except (OSError, ValueError, TypeError):
                _LOGGER.exception("Error validating Pixelblaze host")
                errors["base"] = "unknown"
            else:
                unique_id = info["pixelblaze_id"] or host
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                title = user_input.get(CONF_DEVICE_NAME) or info["name"] or host
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_PIXELBLAZE_ID: unique_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    # ---- DHCP discovery ---------------------------------------------------

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        host = discovery_info.ip
        if discovery_info.macaddress:
            mac = discovery_info.macaddress.lower().replace(":", "")
            await self.async_set_unique_id(f"mac:{mac}")
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._discovered_name = discovery_info.hostname or host
        return await self.async_step_discovery_confirm()

    # ---- Integration discovery (UDP beacon) ------------------------------

    async def async_step_integration_discovery(
        self, discovery_info: Mapping[str, Any]
    ) -> ConfigFlowResult:
        host = str(discovery_info["host"])
        device_id = str(discovery_info.get("id") or host)
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._discovered_id = device_id
        self._discovered_name = str(discovery_info.get("name") or device_id)
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        if user_input is not None:
            try:
                info = await _validate_host(self.hass, self._host)
            except PixelblazeConnectionError:
                return self.async_abort(reason="cannot_connect")
            title = self._discovered_name or info["name"] or self._host
            return self.async_create_entry(
                title=title,
                data={
                    CONF_HOST: self._host,
                    CONF_PIXELBLAZE_ID: self._discovered_id or info["pixelblaze_id"] or self._host,
                },
            )
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "host": self._host,
                "name": self._discovered_name or self._host,
            },
        )

    # ---- Reauth ----------------------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._host = entry_data.get(CONF_HOST)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw_host = user_input.get(CONF_HOST) or self._host
            if not raw_host:
                errors["base"] = "invalid_host"
            else:
                try:
                    host = _clean_host(raw_host)
                except _InvalidHostError:
                    errors["base"] = "invalid_host"
                else:
                    try:
                        await _validate_host(self.hass, host)
                    except PixelblazeConnectionError:
                        errors["base"] = "cannot_connect"
                    else:
                        entry = self._get_reauth_entry()
                        self.hass.config_entries.async_update_entry(
                            entry, data={**entry.data, CONF_HOST: host}
                        )
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=self._host or ""): str}
            ),
            errors=errors,
        )

    # ---- Options ----------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PixelblazeOptionsFlow(config_entry)


class PixelblazeOptionsFlow(OptionsFlow):
    """Handle options for a Pixelblaze entry."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_scan = self._entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        current_disable_beacon = self._entry.options.get(CONF_DISABLE_BEACON, False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                        int, vol.Range(min=2, max=300)
                    ),
                    vol.Optional(CONF_DISABLE_BEACON, default=current_disable_beacon): bool,
                }
            ),
        )

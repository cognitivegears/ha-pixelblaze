"""Registers the Pixelblaze custom services on first config-entry setup.

Service handlers fan out across multiple devices concurrently with
``asyncio.gather`` so a multi-device scene activation doesn't serialize.
Schemas coerce numeric values and cap string lengths to defend the device
(an ESP32) against oversized payloads.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util.hass_dict import HassKey
import voluptuous as vol

from ..api import PixelblazeError
from ..const import (
    ATTR_DEVICE_ID,
    ATTR_HUE,
    ATTR_MODE,
    ATTR_NAME,
    ATTR_PATTERN,
    ATTR_PLAYLIST_ID,
    ATTR_SATURATION,
    ATTR_SEQUENCER_MODE,
    ATTR_VALUE,
    ATTR_VALUE_BRIGHTNESS,
    ATTR_VALUES,
    ATTR_VARIABLES,
    DOMAIN,
    SEQUENCER_NAME_TO_MODE,
    SERVICE_ACTIVATE_SCENE,
    SERVICE_GET_VARIABLES,
    SERVICE_NEXT_PATTERN,
    SERVICE_REFRESH_PATTERN_LIST,
    SERVICE_RUN_PLAYLIST,
    SERVICE_SET_COLOR_CONTROL,
    SERVICE_SET_PATTERN,
    SERVICE_SET_SEQUENCER_MODE,
    SERVICE_SET_VARIABLE,
    SERVICE_SET_VARIABLES,
)

if TYPE_CHECKING:
    from ..coordinator import PixelblazeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_SERVICES_REGISTERED: HassKey[bool] = HassKey(f"{DOMAIN}_services_registered")

# Caps to defend the ESP32 device. The lib JSON-encodes safely so injection is
# not the concern; a 100MB string will hang or brick the device.
_MAX_NAME_LEN = 64
_MAX_VALUE_STR_LEN = 256
_MAX_LIST_LEN = 64
_MAX_DICT_KEYS = 64

_SAFE_NAME = vol.All(str, vol.Length(min=1, max=_MAX_NAME_LEN))


def _finite_float(value: Any) -> float:
    """Coerce to float and reject NaN/Infinity.

    `vol.Coerce(float)` accepts "NaN" and "1e500", which produce non-RFC-7159
    JSON tokens when serialized to the device's websocket. Some firmware
    revisions drop the connection or corrupt state on receipt.

    Wraps the underlying ``TypeError``/``ValueError`` as ``vol.Invalid`` so
    ``vol.Any`` (used to accept ``float | list[float]``) can fall through to
    the list branch when given a list.
    """
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise vol.Invalid(f"value must be a number: {exc}") from exc
    if not math.isfinite(f):
        raise vol.Invalid("value must be a finite number")
    return f


_SAFE_NUM = _finite_float
_SAFE_NUM_LIST = vol.All([_SAFE_NUM], vol.Length(max=_MAX_LIST_LEN))
_SAFE_VAR_VALUE = vol.Any(_SAFE_NUM, _SAFE_NUM_LIST)


def _validate_var_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise vol.Invalid("expected mapping")
    if len(value) > _MAX_DICT_KEYS:
        raise vol.Invalid(f"too many entries (max {_MAX_DICT_KEYS})")
    out: dict[str, Any] = {}
    for k, v in value.items():
        if not isinstance(k, str) or len(k) > _MAX_NAME_LEN:
            raise vol.Invalid("variable name too long or non-string")
        out[k] = _SAFE_VAR_VALUE(v)
    return out


# `cv.ensure_list` wraps a scalar in a list and accepts a list as-is, so service
# handlers always receive ``list[str]`` for device_id without each one needing
# its own normalization step.
_DEVICE_IDS = vol.All(cv.ensure_list, [cv.string])

SET_VARIABLE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Required(ATTR_NAME): _SAFE_NAME,
        vol.Required(ATTR_VALUE): _SAFE_VAR_VALUE,
    }
)
SET_VARIABLES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Required(ATTR_VALUES): _validate_var_dict,
    }
)
SET_PATTERN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Required(ATTR_PATTERN): vol.All(str, vol.Length(min=1, max=_MAX_VALUE_STR_LEN)),
    }
)
NEXT_PATTERN_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS})
SET_SEQUENCER_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Required(ATTR_MODE): vol.In(list(SEQUENCER_NAME_TO_MODE.keys())),
    }
)
SET_COLOR_CONTROL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Required(ATTR_NAME): _SAFE_NAME,
        vol.Required(ATTR_HUE): vol.All(_SAFE_NUM, vol.Range(min=0.0, max=1.0)),
        vol.Required(ATTR_SATURATION): vol.All(_SAFE_NUM, vol.Range(min=0.0, max=1.0)),
        vol.Required(ATTR_VALUE_BRIGHTNESS): vol.All(_SAFE_NUM, vol.Range(min=0.0, max=1.0)),
    }
)
RUN_PLAYLIST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
        vol.Optional(ATTR_PLAYLIST_ID, default="_defaultplaylist_"): vol.All(
            str, vol.Length(max=_MAX_NAME_LEN)
        ),
    }
)
REFRESH_PATTERN_LIST_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS})


# activate_scene: every field except device_id is optional, but at least one
# of the optional fields must be provided — an empty scene is a no-op and
# almost certainly a mistake on the caller's part.
def _at_least_one_scene_field(value: dict[str, Any]) -> dict[str, Any]:
    if not any(
        k in value
        for k in (ATTR_PATTERN, ATTR_VALUE_BRIGHTNESS, ATTR_VARIABLES, ATTR_SEQUENCER_MODE)
    ):
        raise vol.Invalid(
            "activate_scene requires at least one of: pattern, brightness, variables, sequencer_mode"
        )
    return value


ACTIVATE_SCENE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS,
            vol.Optional(ATTR_PATTERN): vol.All(str, vol.Length(min=1, max=_MAX_VALUE_STR_LEN)),
            vol.Optional(ATTR_VALUE_BRIGHTNESS): vol.All(_SAFE_NUM, vol.Range(min=0.0, max=1.0)),
            vol.Optional(ATTR_VARIABLES): _validate_var_dict,
            vol.Optional(ATTR_SEQUENCER_MODE): vol.In(list(SEQUENCER_NAME_TO_MODE.keys())),
        }
    ),
    _at_least_one_scene_field,
)

GET_VARIABLES_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): _DEVICE_IDS})


def _resolve_coordinators(
    hass: HomeAssistant, device_ids: list[str]
) -> list[PixelblazeDataUpdateCoordinator]:
    device_registry = dr.async_get(hass)
    coordinators: list[PixelblazeDataUpdateCoordinator] = []
    for did in device_ids:
        device = device_registry.async_get(did)
        if device is None:
            raise ServiceValidationError(f"Unknown device id: {did}")
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN:
                continue
            runtime = getattr(entry, "runtime_data", None)
            if runtime is None:
                continue
            coordinators.append(runtime.coordinator)
            break
    if not coordinators:
        raise ServiceValidationError(f"No Pixelblaze entries found for: {device_ids}")
    return coordinators


async def _resolve_pattern_id(coordinator: PixelblazeDataUpdateCoordinator, pattern: str) -> str:
    state = coordinator.data
    if state is None:
        raise HomeAssistantError("Coordinator has no state yet")
    pid = state.find_pattern_id(pattern)
    if pid is None:
        raise ServiceValidationError(f"Unknown pattern: {pattern}")
    return pid


def _log_peer_errors(eg: BaseExceptionGroup[BaseException]) -> None:
    """Log second-and-later leaves of an ExceptionGroup at debug.

    Assumes ``eg`` is flat — TaskGroup produces flat groups when leaf tasks
    raise leaf exceptions. Nested TaskGroups would yield nested groups; this
    helper would still work but the debug message would be opaque.
    """
    for peer in eg.exceptions[1:]:
        _LOGGER.debug("Pixelblaze service call (peer) also failed: %s", peer)


async def _gather(coros: list[Any]) -> None:
    """Run coros concurrently with fail-fast TaskGroup semantics.

    On error, sibling tasks are cancelled, peer exceptions logged at debug,
    and the first error is re-raised (wrapped in ``HomeAssistantError`` if
    it's a ``PixelblazeError``).
    """
    try:
        async with asyncio.TaskGroup() as tg:
            for coro in coros:
                tg.create_task(coro)
    except* PixelblazeError as eg_pb:
        _log_peer_errors(eg_pb)
        first = eg_pb.exceptions[0]
        raise HomeAssistantError(str(first)) from first
    except* HomeAssistantError as eg_ha:
        _log_peer_errors(eg_ha)
        raise eg_ha.exceptions[0] from None


def _build_handlers(hass: HomeAssistant) -> dict[str, Any]:  # noqa: PLR0915
    """Construct service handlers as closures over ``hass``.

    Each handler is small (3-15 lines), but ten of them in one function pushes
    the total statement count past the lint threshold. The alternatives —
    splitting into multiple builders or moving handlers to module scope with
    ``hass`` threaded as an argument — make the code harder to read for
    no real benefit, since the handlers are tightly cohesive.
    """

    async def _set_variable(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather(
            [
                c.async_set_active_variables({call.data[ATTR_NAME]: call.data[ATTR_VALUE]})
                for c in coords
            ]
        )

    async def _set_variables(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        values = dict(call.data[ATTR_VALUES])
        await _gather([c.async_set_active_variables(values) for c in coords])

    async def _set_pattern(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        pattern = call.data[ATTR_PATTERN]

        async def _one(c: PixelblazeDataUpdateCoordinator) -> None:
            pid = await _resolve_pattern_id(c, pattern)
            await c.async_set_pattern(pid)

        await _gather([_one(c) for c in coords])

    async def _next_pattern(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather([c.async_next_pattern() for c in coords])

    async def _set_sequencer_mode(call: ServiceCall) -> None:
        mode = SEQUENCER_NAME_TO_MODE[call.data[ATTR_MODE]]
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather([c.async_set_sequencer_mode(mode) for c in coords])

    async def _set_color_control(call: ServiceCall) -> None:
        name = call.data[ATTR_NAME]
        hsv = [
            float(call.data[ATTR_HUE]),
            float(call.data[ATTR_SATURATION]),
            float(call.data[ATTR_VALUE_BRIGHTNESS]),
        ]
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather([c.async_set_color_control(name, hsv) for c in coords])

    async def _run_playlist(call: ServiceCall) -> None:
        playlist_id = call.data[ATTR_PLAYLIST_ID]
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather([c.async_run_playlist(playlist_id) for c in coords])

    async def _refresh_pattern_list(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        await _gather([c.async_refresh_pattern_list() for c in coords])

    async def _activate_scene(call: ServiceCall) -> None:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        pattern = call.data.get(ATTR_PATTERN)
        brightness = call.data.get(ATTR_VALUE_BRIGHTNESS)
        variables = call.data.get(ATTR_VARIABLES)
        seq_name = call.data.get(ATTR_SEQUENCER_MODE)
        seq_mode = SEQUENCER_NAME_TO_MODE[seq_name] if seq_name is not None else None

        async def _one(c: PixelblazeDataUpdateCoordinator) -> None:
            pattern_id = await _resolve_pattern_id(c, pattern) if pattern else None
            await c.async_activate_scene(
                pattern_id=pattern_id,
                brightness=brightness,
                variables=dict(variables) if variables else None,
                sequencer_mode=seq_mode,
            )

        await _gather([_one(c) for c in coords])

    async def _get_variables(call: ServiceCall) -> ServiceResponse:
        coords = _resolve_coordinators(hass, call.data[ATTR_DEVICE_ID])
        # ``_resolve_coordinators`` already validates that we got at least one
        # entry; map device_id -> variables so callers can correlate even when
        # a device_id alias resolved to the same coordinator twice.
        device_registry = dr.async_get(hass)
        result: dict[str, dict[str, Any]] = {}
        for did in call.data[ATTR_DEVICE_ID]:
            device = device_registry.async_get(did)
            if device is None:
                continue
            for entry_id in device.config_entries:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry is None or entry.domain != DOMAIN:
                    continue
                runtime = getattr(entry, "runtime_data", None)
                if runtime is None:
                    continue
                state = runtime.coordinator.data
                result[did] = dict(state.active_variables) if state else {}
                break
        # Touch ``coords`` so unused-var lint doesn't complain — also ensures
        # the resolution side-effects (validation errors) actually run.
        _ = coords
        # ServiceResponse's nominal value type is ``JsonValueType`` (recursive),
        # but our nested ``dict[str, Any]`` is JSON-safe in practice — the
        # contents are device-side primitives the upstream lib already serializes.
        return cast(ServiceResponse, {"devices": result})

    return {
        SERVICE_SET_VARIABLE: _set_variable,
        SERVICE_SET_VARIABLES: _set_variables,
        SERVICE_SET_PATTERN: _set_pattern,
        SERVICE_NEXT_PATTERN: _next_pattern,
        SERVICE_SET_SEQUENCER_MODE: _set_sequencer_mode,
        SERVICE_SET_COLOR_CONTROL: _set_color_control,
        SERVICE_RUN_PLAYLIST: _run_playlist,
        SERVICE_REFRESH_PATTERN_LIST: _refresh_pattern_list,
        SERVICE_ACTIVATE_SCENE: _activate_scene,
        SERVICE_GET_VARIABLES: _get_variables,
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Pixelblaze services. Idempotent."""
    if hass.data.get(_SERVICES_REGISTERED):
        return
    hass.data[_SERVICES_REGISTERED] = True

    handlers = _build_handlers(hass)

    # (service_name, schema, supports_response). Handler resolved via ``handlers``.
    registrations: tuple[tuple[str, vol.Schema | vol.All, SupportsResponse], ...] = (
        (SERVICE_SET_VARIABLE, SET_VARIABLE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_SET_VARIABLES, SET_VARIABLES_SCHEMA, SupportsResponse.NONE),
        (SERVICE_SET_PATTERN, SET_PATTERN_SCHEMA, SupportsResponse.NONE),
        (SERVICE_NEXT_PATTERN, NEXT_PATTERN_SCHEMA, SupportsResponse.NONE),
        (SERVICE_SET_SEQUENCER_MODE, SET_SEQUENCER_MODE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_SET_COLOR_CONTROL, SET_COLOR_CONTROL_SCHEMA, SupportsResponse.NONE),
        (SERVICE_RUN_PLAYLIST, RUN_PLAYLIST_SCHEMA, SupportsResponse.NONE),
        (SERVICE_REFRESH_PATTERN_LIST, REFRESH_PATTERN_LIST_SCHEMA, SupportsResponse.NONE),
        (SERVICE_ACTIVATE_SCENE, ACTIVATE_SCENE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_GET_VARIABLES, GET_VARIABLES_SCHEMA, SupportsResponse.ONLY),
    )
    for name, schema, response in registrations:
        hass.services.async_register(
            DOMAIN, name, handlers[name], schema=schema, supports_response=response
        )

"""Regression tests for the executor-pool-poisoning fix.

The integration calls a synchronous Pixelblaze client library through
``hass.async_add_executor_job``. Without bounds, an unreachable device pins
a SyncWorker thread inside ``sock.connect`` for the full kernel TCP timeout
(~75s on Linux). With multiple offline devices the executor pool fills and
Home Assistant Core hangs.

These tests pin the two-layer defense in place:

1. An async TCP-reachability pre-flight runs before any executor dispatch.
   When it fails, no executor work is queued at all.
2. The executor dispatch itself is wrapped in ``asyncio.timeout`` so a
   device that accepts TCP but stalls during the websocket handshake
   surfaces as a bounded failure rather than blocking the event loop.

Plus the coordinator-level circuit breaker that backs off the poll cadence
when a device has been unreachable for several cycles.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.pixelblaze.api import (
    PixelblazeClient,
    PixelblazeConnectionError,
)
from custom_components.pixelblaze.const import DOMAIN
from custom_components.pixelblaze.coordinator import (
    _BACKOFF_AFTER_FAILURES,
    _BACKOFF_CEILING,
    PixelblazeDataUpdateCoordinator,
)


async def _make_client(hass: Any) -> PixelblazeClient:
    client = PixelblazeClient(hass, "1.2.3.4")
    await client.async_connect()
    return client


async def _make_coordinator(hass: Any) -> PixelblazeDataUpdateCoordinator:
    from homeassistant.config_entries import ConfigEntry

    client = await _make_client(hass)
    entry = ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test",
        data={"host": "1.2.3.4"},
        source="user",
        unique_id="pb:deadbeef",
        options={},
        discovery_keys={},
        subentries_data=None,
    )
    return PixelblazeDataUpdateCoordinator(hass, entry, client)


async def test_unreachable_device_skips_executor(hass: Any) -> None:
    """Pre-flight failure must raise before any executor dispatch happens."""
    client = await _make_client(hass)
    # Already connected; the next fetch_state pre-flights again.
    with (
        patch(
            "custom_components.pixelblaze.api.async_is_reachable",
            return_value=False,
        ),
        patch.object(hass, "async_add_executor_job", side_effect=AssertionError("must not run")),
        pytest.raises(PixelblazeConnectionError),
    ):
        await client.async_fetch_state(None)


async def test_unreachable_returns_quickly(hass: Any) -> None:
    """An unreachable device must surface as UpdateFailed within seconds."""
    coord = await _make_coordinator(hass)
    with patch(
        "custom_components.pixelblaze.api.async_is_reachable",
        return_value=False,
    ):
        async with asyncio.timeout(3.0):
            await coord.async_refresh()
    assert not coord.last_update_success


async def test_stalled_executor_call_is_bounded(hass: Any) -> None:
    """Device accepts TCP but never responds; executor dispatch is cancelled."""
    client = await _make_client(hass)
    client._operation_timeout = 0.2  # tight bound for the test

    def _block_forever(*_args: Any, **_kwargs: Any) -> Any:
        # Simulate a wedged sync call: this would run in the real executor and
        # the asyncio.timeout would cancel the awaiter even if the thread
        # itself kept going. The mock returns immediately so we can assert
        # the wait_for boundary; we approximate "stalled" by making the
        # awaitable never complete.
        loop = asyncio.get_event_loop()
        return loop.create_future()  # never resolves

    with (
        patch.object(hass, "async_add_executor_job", side_effect=_block_forever),
        pytest.raises(PixelblazeConnectionError),
    ):
        await client.async_fetch_state(None)


async def test_circuit_breaker_backs_off_after_repeated_failures(hass: Any) -> None:
    """After N consecutive failures the poll interval grows up to the ceiling."""
    coord = await _make_coordinator(hass)
    base = coord.update_interval
    assert base is not None

    with patch(
        "custom_components.pixelblaze.api.async_is_reachable",
        return_value=False,
    ):
        # First failures below the threshold leave the interval untouched.
        for _ in range(_BACKOFF_AFTER_FAILURES - 1):
            await coord.async_refresh()
        assert coord.update_interval == base

        # The threshold-crossing failure expands the interval.
        await coord.async_refresh()
        assert coord.update_interval is not None
        assert coord.update_interval > base

        # Many more failures cap at the ceiling.
        for _ in range(20):
            await coord.async_refresh()
        assert coord.update_interval == _BACKOFF_CEILING


async def test_circuit_breaker_resets_on_recovery(hass: Any) -> None:
    """A successful poll restores the base interval and clears the counter."""
    coord = await _make_coordinator(hass)
    base = coord.update_interval

    with patch(
        "custom_components.pixelblaze.api.async_is_reachable",
        return_value=False,
    ):
        for _ in range(_BACKOFF_AFTER_FAILURES + 2):
            await coord.async_refresh()
    assert coord.update_interval is not None
    assert coord.update_interval != base

    # Device recovers. The next refresh succeeds (default fake reachability
    # via the autouse fixture restores the True branch when the patch exits).
    await coord.async_refresh()
    assert coord.last_update_success
    assert coord.update_interval == base


async def test_force_reconnect_close_is_bounded(hass: Any) -> None:
    """Force-reconnect must not block on a wedged websocket close."""
    client = await _make_client(hass)
    # Wedge the executor dispatch used by _sync_close.
    blocking_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()

    async def _hang(*_a: Any, **_kw: Any) -> None:
        await blocking_future  # never resolves

    with patch.object(hass, "async_add_executor_job", side_effect=_hang):
        # Should return within the 2s internal timeout rather than hanging.
        async with asyncio.timeout(3.0):
            await client._force_reconnect()

    assert client._pb is None

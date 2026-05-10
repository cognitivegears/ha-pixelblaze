"""Defensive UDP beacon listener for Pixelblaze auto-discovery.

Pixelblaze devices broadcast a beacon packet on UDP port 1889 every second.
We listen passively and spawn a config-flow ``integration_discovery`` for each
new device.

This implementation is **defensive**:
- If the port cannot be bound (already in use, no permission, container without
  host networking), we log a single warning and disable auto-discovery without
  raising. The integration continues to work via DHCP and manual setup.
- A token-bucket rate limit (50 packets/second) prevents a malicious LAN host
  from flooding the listener with crafted beacons to spawn unbounded flow inits.
- The ``_seen`` dedup map is capped at 1024 entries with TTL-based eviction so
  random ``sender_id`` floods cannot cause unbounded memory growth.
- Beacon packets larger than 256 bytes are dropped before parsing.
- The optional name field is length-capped and stripped of control characters
  to prevent ANSI-escape / log-injection attacks via diagnostic dumps.
- The listener is reference-counted: the first entry that opts in starts it,
  and it stops when the last entry unloads.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import struct
import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.util.hass_dict import HassKey

from .const import BEACON_DEDUP_TTL, BEACON_PORT, BEACON_TYPE_DEVICE, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_BEACON_LISTENER_KEY: HassKey[PixelblazeBeaconListener] = HassKey(f"{DOMAIN}_beacon_listener")

_MAX_PACKET_BYTES = 256
_MAX_NAME_LEN = 64
_MAX_SEEN = 1024
_PACKET_RATE_PER_SEC = 50.0


def _sanitize_name(raw: bytes) -> str | None:
    """Decode and sanitize a beacon name field.

    Returns ``None`` if the bytes can't be decoded or yield no printable text.
    Strips control chars, ANSI escapes, and bidirectional-override codepoints
    that could interleave fake log lines or rewrite terminal state when an
    operator views logs or diagnostic dumps.
    """
    if not raw:
        return None
    try:
        decoded = raw.rstrip(b"\x00")[:_MAX_NAME_LEN].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    # Drop bidirectional-override codepoints that could rewrite terminals.
    # LRE U+202A, RLE U+202B, PDF U+202C, LRO U+202D, RLO U+202E.
    bidi_override = frozenset(chr(c) for c in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E))
    cleaned = "".join(ch for ch in decoded if ch.isprintable() and ch not in bidi_override)
    cleaned = cleaned.strip()
    return cleaned[:_MAX_NAME_LEN] or None


def _parse_beacon(data: bytes) -> dict[str, Any] | None:
    """Parse a Pixelblaze beacon packet.

    Returns ``None`` for packets that are not a valid type-42 device beacon.
    Layout (little-endian): ``uint32 packet_type | uint32 sender_id | uint32 sender_time``
    plus an optional trailing UTF-8 device name.
    """
    if len(data) < 12 or len(data) > _MAX_PACKET_BYTES:
        return None
    try:
        packet_type, sender_id, sender_time = struct.unpack_from("<III", data, 0)
    except struct.error:
        return None
    if packet_type != BEACON_TYPE_DEVICE:
        return None
    name = _sanitize_name(data[12:]) if len(data) > 12 else None
    return {
        "packet_type": packet_type,
        "sender_id": sender_id,
        "sender_time": sender_time,
        "name": name,
    }


class _BeaconProtocol(asyncio.DatagramProtocol):
    """Datagram protocol that hands beacon hits off to the listener."""

    def __init__(self, listener: PixelblazeBeaconListener) -> None:
        self._listener = listener

    def datagram_received(self, data: bytes, addr: tuple[Any, ...]) -> None:
        # Bare ``except Exception`` here is required by asyncio's contract:
        # an uncaught exception breaks the transport. We log at debug to keep
        # the loop alive; legitimate handler bugs surface in unit tests.
        try:
            self._listener.handle_packet(data, addr)
        except Exception as exc:
            _LOGGER.debug("Beacon handler error (ignored): %s", exc)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("Beacon transport error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None:
            _LOGGER.debug("Beacon transport lost: %s", exc)


class PixelblazeBeaconListener:
    """Owns the UDP beacon socket and dispatches discoveries.

    Lifecycle: reference-counted — call ``async_acquire`` from each entry that
    opts in, and ``async_release`` on unload. The listener stops and frees its
    socket when the last reference is released.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._transport: asyncio.DatagramTransport | None = None
        self._seen: dict[int, float] = {}
        self._enabled = True
        self._refcount = 0
        self._tokens = _PACKET_RATE_PER_SEC
        self._last_tick = time.monotonic()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def async_acquire(self) -> bool:
        """Increment the user count; start the listener on first acquire.

        Returns True if the listener is active after acquire. False means the
        port couldn't be bound (already in use, etc.) and discovery is
        disabled — but acquire is still counted so release semantics are
        symmetric.
        """
        self._refcount += 1
        if self._transport is None and self._enabled:
            return await self.async_start()
        return self._transport is not None

    async def async_release(self) -> None:
        """Decrement the user count; stop the listener when the last user releases."""
        self._refcount = max(0, self._refcount - 1)
        if self._refcount == 0:
            await self.async_stop()
            self._hass.data.pop(_BEACON_LISTENER_KEY, None)

    async def async_start(self) -> bool:
        """Bind the UDP socket. Returns True if listening, False if disabled."""
        if self._transport is not None:
            return True
        loop = asyncio.get_running_loop()

        def _make_socket() -> socket.socket | None:
            sock: socket.socket | None = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                with contextlib.suppress(OSError):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                with contextlib.suppress(OSError):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(("0.0.0.0", BEACON_PORT))
                sock.setblocking(False)
            except OSError as exc:
                if sock is not None:
                    sock.close()
                _LOGGER.warning(
                    "Pixelblaze auto-discovery disabled: could not bind UDP %d (%s). "
                    "Manual setup and DHCP discovery still work.",
                    BEACON_PORT,
                    exc,
                )
                return None
            else:
                return sock

        sock = await loop.run_in_executor(None, _make_socket)
        if sock is None:
            self._enabled = False
            return False

        try:
            transport, _proto = await loop.create_datagram_endpoint(
                lambda: _BeaconProtocol(self),
                sock=sock,
            )
        except Exception as exc:
            _LOGGER.warning("Pixelblaze beacon listener failed to start: %s", exc)
            with contextlib.suppress(OSError):
                sock.close()
            self._enabled = False
            return False

        self._transport = transport
        _LOGGER.debug("Pixelblaze beacon listener bound to UDP %d", BEACON_PORT)
        return True

    async def async_stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._seen.clear()

    def handle_packet(self, data: bytes, addr: tuple[Any, ...]) -> None:
        # Token-bucket rate limit. Refill at _PACKET_RATE_PER_SEC tokens/sec,
        # capped at one second's worth. Drop the packet if the bucket is empty.
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_tick)
        self._tokens = min(_PACKET_RATE_PER_SEC, self._tokens + elapsed * _PACKET_RATE_PER_SEC)
        self._last_tick = now
        if self._tokens < 1.0:
            return
        self._tokens -= 1.0

        info = _parse_beacon(data)
        if info is None:
            return
        sender_id = int(info["sender_id"])

        # TTL-based dedup. Reject duplicates inside the window.
        last = self._seen.get(sender_id)
        if last is not None and (now - last) < BEACON_DEDUP_TTL:
            self._seen[sender_id] = now
            return

        # Bound the dedup map so a flood of random sender_ids can't OOM us.
        if len(self._seen) >= _MAX_SEEN:
            cutoff = now - BEACON_DEDUP_TTL
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            if len(self._seen) >= _MAX_SEEN:
                # Even after eviction, drop oldest to make room.
                oldest = min(self._seen, key=self._seen.__getitem__)
                self._seen.pop(oldest, None)

        self._seen[sender_id] = now

        host = addr[0] if addr else None
        if not host:
            return
        device_id = f"pb:{sender_id:08x}"
        self._hass.async_create_task(
            self._hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={
                    "host": str(host),
                    "id": device_id,
                    "name": info.get("name"),
                },
            )
        )


async def async_get_beacon_listener(hass: HomeAssistant) -> PixelblazeBeaconListener:
    """Return the singleton beacon listener, creating it on first use.

    Note: callers are expected to ``async_acquire``/``async_release`` so the
    listener is stopped when the last entry unloads.
    """
    listener: PixelblazeBeaconListener | None = hass.data.get(_BEACON_LISTENER_KEY)
    if listener is None:
        listener = PixelblazeBeaconListener(hass)
        hass.data[_BEACON_LISTENER_KEY] = listener
    return listener

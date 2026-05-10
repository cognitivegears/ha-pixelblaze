"""Diagnostics for Pixelblaze config entries.

HA users routinely upload diagnostics to public GitHub issues. We aggressively
redact:
- ``host`` / ``ip`` (network identifiers)
- ``title`` (often the IP if the user accepted the default during setup)
- ``name`` (user-set device label, sometimes contains family info)
- ``pixelblaze_id`` (stable hardware identifier; correlates to a serial)
- pattern names and active variables (user content; may contain personal info
  in pattern names like "Sarah's Birthday")
- playlist items (same)

We surface counts so debuggers can still see "this device has 47 patterns"
without the names themselves.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import PixelblazeConfigEntry

TO_REDACT = {
    "host",
    "ip",
    "name",
    "pixelblaze_id",
    "active_pattern_name",
    "pattern_list",
    "pattern_label_to_id",
    "active_variables",
    "playlist_items",
    "playlist_id",
    "active_controls",
}


def _redact_title(title: str | None, host: str) -> str:
    """Redact the entry title unconditionally.

    The title is operator-chosen and frequently contains personal info
    ("Sarah's Birthday", "Kid's Room"). Diagnostic dumps are routinely
    uploaded to public GitHub issues; we redact in full and surface only
    the length as a debug hint.
    """
    del host  # title is redacted regardless of host
    if not title:
        return ""
    return f"**REDACTED ({len(title)} chars)**"


def _summarize(state_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace user content with counts/booleans."""
    summary = dict(state_dict)
    if "pattern_list" in summary and isinstance(summary["pattern_list"], dict):
        summary["pattern_count"] = len(summary["pattern_list"])
    if "active_variables" in summary and isinstance(summary["active_variables"], dict):
        summary["active_variable_count"] = len(summary["active_variables"])
    if "active_controls" in summary and isinstance(summary["active_controls"], dict):
        summary["active_control_keys"] = sorted(summary["active_controls"].keys())
    if "playlist_items" in summary and isinstance(summary["playlist_items"], list):
        summary["playlist_item_count"] = len(summary["playlist_items"])
    return summary


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PixelblazeConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    state = coordinator.data
    state_dict = asdict(state) if state else {}
    summarized = _summarize(state_dict)
    return {
        "entry": {
            "title": _redact_title(entry.title, entry.data.get("host", "")),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id": "**REDACTED**" if entry.unique_id else None,
        },
        "state": async_redact_data(summarized, TO_REDACT),
    }

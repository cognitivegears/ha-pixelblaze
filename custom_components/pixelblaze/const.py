"""Constants for the Pixelblaze integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "pixelblaze"
MANUFACTURER: Final = "ElectroMage"
MODEL: Final = "Pixelblaze"

CONF_HOST: Final = "host"
CONF_PIXELBLAZE_ID: Final = "pixelblaze_id"
CONF_DEVICE_NAME: Final = "name"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_DISABLE_BEACON: Final = "disable_beacon_listener"

DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=10)
PATTERN_LIST_REFRESH_INTERVAL: Final = timedelta(minutes=5)

DEFAULT_PORT: Final = 81  # Pixelblaze websocket port
BEACON_PORT: Final = 1889  # UDP discovery beacon port
BEACON_TYPE_DEVICE: Final = 42  # Pixelblaze beacon packet type
BEACON_DEDUP_TTL: Final = 60.0  # seconds

# Sequencer modes (from pixelblaze.sequencerModes)
SEQUENCER_MODE_OFF: Final = 0
SEQUENCER_MODE_SHUFFLE: Final = 1
SEQUENCER_MODE_PLAYLIST: Final = 2

SEQUENCER_MODE_NAMES: Final = {
    SEQUENCER_MODE_OFF: "off",
    SEQUENCER_MODE_SHUFFLE: "shuffle_all",
    SEQUENCER_MODE_PLAYLIST: "playlist",
}
SEQUENCER_NAME_TO_MODE: Final = {v: k for k, v in SEQUENCER_MODE_NAMES.items()}

# Service names
SERVICE_SET_VARIABLE: Final = "set_variable"
SERVICE_SET_VARIABLES: Final = "set_variables"
SERVICE_SET_PATTERN: Final = "set_pattern"
SERVICE_NEXT_PATTERN: Final = "next_pattern"
SERVICE_SET_SEQUENCER_MODE: Final = "set_sequencer_mode"
SERVICE_SET_COLOR_CONTROL: Final = "set_color_control"
SERVICE_RUN_PLAYLIST: Final = "run_playlist"
SERVICE_REFRESH_PATTERN_LIST: Final = "refresh_pattern_list"
SERVICE_ACTIVATE_SCENE: Final = "activate_scene"
SERVICE_GET_VARIABLES: Final = "get_variables"

# Service field names
ATTR_DEVICE_ID: Final = "device_id"
ATTR_NAME: Final = "name"
ATTR_VALUE: Final = "value"
ATTR_VALUES: Final = "values"
ATTR_PATTERN: Final = "pattern"
ATTR_MODE: Final = "mode"
ATTR_PLAYLIST_ID: Final = "playlist_id"
ATTR_HUE: Final = "hue"
ATTR_SATURATION: Final = "saturation"
ATTR_VALUE_BRIGHTNESS: Final = "brightness"
ATTR_VARIABLES: Final = "variables"
ATTR_SEQUENCER_MODE: Final = "sequencer_mode"

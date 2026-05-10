# Features

Full reference for entities and services exposed by the Pixelblaze integration.

## Entities

| Platform | Entity | Notes |
| --- | --- | --- |
| `light` | Pixelblaze main light | Brightness, on/off, `effect_list` from device pattern names |
| `light` | Color pickers | One HS-color light per `hsvPicker*` control on the active pattern; `unavailable` when the active pattern doesn't expose it |
| `select` | Pattern | Switch patterns by name |
| `select` | Sequencer mode | Off / Shuffle / Playlist |
| `number` | Pattern controls | One slider per `slider*` control on the active pattern; appears and disappears with the pattern |
| `switch` | Sequencer | Quick on/off for shuffle |
| `sensor` | FPS, uptime, firmware version, free storage, LED count, IP | |
| `button` | Next pattern, reboot | |
| `update` | Firmware version | Read-only — see [limitations](limitations.md) |

## Services

| Service | Purpose |
| --- | --- |
| `pixelblaze.set_pattern` | Switch to a pattern by name or id |
| `pixelblaze.next_pattern` | Advance to the next pattern |
| `pixelblaze.set_variable` | Set one exported variable on the active pattern |
| `pixelblaze.set_variables` | Set multiple exported variables in one call |
| `pixelblaze.get_variables` | Read the active pattern's exported variables (response service) |
| `pixelblaze.set_color_control` | Set an `hsvPicker*` / `rgbPicker*` control directly |
| `pixelblaze.set_sequencer_mode` | Off / Shuffle / Playlist |
| `pixelblaze.run_playlist` | Switch into the device's default playlist |
| `pixelblaze.refresh_pattern_list` | Re-read patterns from the device after editing them in the web UI |
| `pixelblaze.activate_scene` | Atomically apply pattern + brightness + variables + sequencer mode in one call |

`activate_scene` is the right tool for "set the lights for movie mode" — it takes the per-device lock once and emits a single optimistic state patch, so subscribers see one transition rather than three or four flickers.

`set_variable` / `set_variables` accept numbers and lists of numbers only. Strings and booleans are rejected at the schema layer to avoid sending malformed payloads to the device.

See [automations.md](automations.md) for end-to-end examples.

## Discovery

- **DHCP matcher** — hosts named `pixelblaze*` or `pb-*` are detected as they appear on the network.
- **UDP beacon listener** — the integration listens on UDP port 1889 (with `SO_REUSEADDR`, defensive `OSError` handling, and TTL-based dedup) and dispatches new beacons through the integration discovery flow.

Auto-discovery can be disabled per Home Assistant instance from the integration's options — see [configuration.md](configuration.md).

## Diagnostics

The integration exposes diagnostics with sensitive fields redacted: entry title, host, IP, Pixelblaze id, device name, pattern names, active controls, active variables, and playlist data. Download from the device page in **Settings → Devices & Services**.

# Limitations

## What's intentionally not in v1

| Area | Why |
| --- | --- |
| Pattern editing / uploading / decompiling | Requires `mini-racer` (V8), which is platform-fragile in Home Assistant container environments |
| EPE pack/unpack | Same `mini-racer` dependency |
| Multi-device clock synchronization | Out of scope for the initial release |
| mDNS auto-discovery | Pixelblaze does not advertise mDNS; DHCP and the UDP beacon cover the common cases |

## Known runtime limitations

- **Playlists** — `pixelblaze.run_playlist` only switches into the device's *default* playlist (`_defaultplaylist_`). This is a Pixelblaze firmware limitation: upstream `pixelblaze-client` documents *"only `_defaultplaylist_` is supported by the Pixelblaze."* Selecting a non-default playlist by id raises an error rather than silently loading the wrong content. Use the Pixelblaze web UI to pick the active playlist.
- **Firmware update detection** — the update entity always reads "up to date" because no upstream version-detection is wired up yet. The installed-version sensor is accurate; trigger upgrades from the device's web UI.
- **Variable values** — `pixelblaze.set_variable` and `pixelblaze.set_variables` accept numbers and lists of numbers only. Strings and booleans are rejected at the schema layer to prevent the device from receiving malformed payloads. NaN and Infinity are also rejected (they don't round-trip cleanly through JSON).
- **Duplicate pattern names** — see [troubleshooting](troubleshooting.md#pattern-name-collisions).

## Feature matrix

| Area | Status |
| --- | --- |
| Brightness, on/off, pattern selection | included |
| Pattern variable / control runtime updates | included |
| Color picker controls (light entity + `set_color_control` service) | included |
| FPS / uptime / version / storage sensors | included |
| Update entity (firmware version surface, read-only) | included (no install action yet) |
| Auto-discovery (DHCP + UDP beacon, defensive) | included |
| Pattern editing / uploading / decompiling | not in v1 |
| EPE pack/unpack | not in v1 |
| Multi-device clock synchronization | not in v1 |
| mDNS auto-discovery | not applicable |

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Color-picker `light` entities. Every `hsvPicker*` control exported by the
  active pattern surfaces as its own `light` entity with `ColorMode.HS` and
  brightness mapped to the V channel of the picker's HSV value. Becomes
  `unavailable` when the active pattern doesn't expose the control. Replaces
  needing to call `pixelblaze.set_color_control` from YAML for the common case.
- `pixelblaze.activate_scene` service — atomically apply pattern, brightness,
  variables, and sequencer mode in a single call under the per-device lock.
  At least one of the optional fields must be provided. Emits one optimistic
  state patch at the end so subscribers see one coherent transition rather
  than four flickers.
- `pixelblaze.get_variables` service — returns a response (`SupportsResponse.ONLY`)
  with the active pattern's exported variables keyed by `device_id`. Lets
  scripts read variable state for templating without watching coordinator
  state through a sensor.

## [0.1.0] - 2026-05-09

Initial public release.

### Requirements

- Home Assistant 2025.1.0 or later (Python 3.13).
- Python 3.13.2+.

### Added

- UI config flow with three discovery sources: manual entry, DHCP matcher,
  and integration-discovery via a defensive UDP beacon listener on port 1889.
- `light` entity with brightness, on/off, and `effect_list` populated from
  the device's pattern names.
- `select` entities for the active pattern and sequencer mode (off / shuffle /
  playlist).
- Dynamic `number` entities for slider controls exposed by the active pattern;
  appear/disappear as patterns change.
- `switch` entity for the sequencer (off / shuffle).
- `sensor` entities for FPS, uptime, firmware version, free storage, LED
  count, and IP.
- `button` entities for next pattern and reboot.
- `update` entity surfacing the installed firmware version (read-only — no
  upstream version detection yet).
- Custom services: `pixelblaze.set_variable`, `set_variables`, `set_pattern`,
  `next_pattern`, `set_sequencer_mode`, `set_color_control`, `run_playlist`,
  `refresh_pattern_list`.
- DataUpdateCoordinator polling at 10 s default with optimistic state
  updates so user-driven changes are reflected immediately.
- Per-device `asyncio.Lock` and `asyncio.timeout` wrapping all websocket
  calls so a hung Pixelblaze can't pin Home Assistant's executor pool.
- Reference-counted UDP beacon listener with token-bucket rate limit
  (50 packets/sec) and bounded dedup map (1024 entries).
- Diagnostics with PII redaction: entry title (unconditional), host, IP,
  Pixelblaze id, device name, pattern names, active controls, active
  variables, and playlist data.

### Validation

- `set_variable`, `set_variables`, and `set_color_control` reject NaN and
  Infinity values at the schema layer (would otherwise serialize to
  non-RFC-7159 JSON tokens that some Pixelblaze firmware revisions reject).
- The host field rejects link-local, loopback, multicast, and unspecified
  IP addresses, scheme-prefixed URLs, paths, and whitespace.
- Saving the options form without changing any values no longer triggers
  a full entity reload.

### Known limitations

- `run_playlist` only activates the default playlist; non-default
  `playlist_id` values raise a clear error rather than silently doing
  the wrong thing.
- Firmware update detection is not yet implemented; the update entity
  always reads "up to date".
- Pattern names that collide on the device are presented as
  `Name (idprefix)` to disambiguate.
- Pattern editing / uploading / decompiling and EPE pack/unpack are
  intentionally deferred (require `mini-racer` / V8).
- Pixelblaze does not advertise mDNS, so zeroconf-style discovery is
  not supported. DHCP and UDP beacon discovery cover the common cases.

[Unreleased]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cognitivegears/ha-pixelblaze/releases/tag/v0.1.0

# Pixelblaze for Home Assistant

[![Validate](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hacs.yml)

A modern, full-coverage Home Assistant integration for [Pixelblaze](https://www.bhencke.com/pixelblaze)
WiFi LED controllers. Built on top of [`pixelblaze-client`](https://github.com/zranger1/pixelblaze-client).

## Features

- **UI setup** — no YAML required.
- **Auto-discovery** — DHCP matcher plus a defensive UDP beacon listener (port 1889).
- **Light entity** — brightness, on/off, and `effect_list` populated from the device's pattern names.
- **Color-picker lights** — every `hsvPicker*` control exported by the active pattern is
  surfaced as its own HS-color light entity, so you get a real color swatch in the UI.
- **Pattern picker** (`select`) — switch patterns by name with a dedicated entity.
- **Sequencer mode** (`select`) — Off / Shuffle / Playlist.
- **Per-pattern controls** (`number`) — slider controls exported by the active pattern surface as
  Home Assistant number entities and update on pattern change.
- **Sequencer toggle** (`switch`) — quick on/off for shuffle.
- **Sensors** — FPS, uptime, firmware version, free storage, LED count, IP.
- **Buttons** — next pattern, reboot.
- **Update entity** — surfaces the device's installed firmware version. There is no
  upstream version-detection yet, so the entity always reads "up to date"; run firmware
  updates from the Pixelblaze web UI for now.
- **Custom services** — `set_variable`, `set_variables`, `set_pattern`, `next_pattern`,
  `set_sequencer_mode`, `set_color_control`, `run_playlist`, `refresh_pattern_list`,
  `activate_scene` (atomic pattern + brightness + variables + sequencer mode), and
  `get_variables` (returns a response with the active pattern's exported variables).
- **Diagnostics** — entry/state dump with sensitive fields redacted.

## What's included in v1.0 / What's not

| Area | Status |
| --- | --- |
| Brightness, on/off, pattern selection | included |
| Pattern variable / control runtime updates | included |
| Color picker controls (via `set_color_control` service) | included |
| FPS / uptime / version / storage sensors | included |
| Update entity (firmware version surface, read-only) | included (no install action yet) |
| Auto-discovery (DHCP + UDP beacon, defensive) | included |
| Pattern editing / uploading / decompiling | **not in v1** — requires `mini-racer` (V8) which is platform-fragile |
| EPE pack/unpack | **not in v1** — same dependency caveat |
| Multi-device clock synchronization | **not in v1** |
| mDNS auto-discovery | **not applicable** — Pixelblaze does not advertise mDNS |

## Known limitations (v0.1.0)

- **Playlists** — `pixelblaze.run_playlist` only switches into the device's *default*
  playlist (`_defaultplaylist_`). This is a Pixelblaze firmware limitation, not an
  integration limitation: upstream `pixelblaze-client` documents *"only `_defaultplaylist_`
  is supported by the Pixelblaze."* Selecting a non-default playlist by id raises an
  error rather than silently loading the wrong content. Use the Pixelblaze web UI to
  pick the active playlist.
- **Update detection** — the firmware update entity always reads "up to date" because
  no upstream version-detection is wired up yet. The installed-version sensor is
  accurate; trigger upgrades from the device's web UI.
- **Duplicate pattern names** — when two patterns on the device share a name, the
  integration appends a 6-character id prefix to disambiguate, e.g. `Sparkles (KGksY)`.
  Automations targeting patterns by name must use this exact label, or pass the pattern
  id directly. Pattern ids are visible via diagnostics and the `pixelblaze.set_pattern`
  service trace.
- **Variable values** — `pixelblaze.set_variable` and `pixelblaze.set_variables` accept
  numbers and lists of numbers only. Strings and booleans are rejected at the schema
  layer to prevent the device from receiving malformed payloads.

## Requirements

- Home Assistant **2025.1.0** or later (Python 3.13 — first shipped in HA Core 2024.12).
- A Pixelblaze with reachable IP/hostname on the local network.

## Installation (HACS)

1. Open HACS → **Integrations** → **⋮** → **Custom repositories**.
2. Add `https://github.com/cognitivegears/ha-pixelblaze` with type **Integration**.
3. Install **Pixelblaze**.
4. Restart Home Assistant.
5. **Settings → Devices & Services → Add Integration → Pixelblaze**, enter the device's IP or
   hostname.

After install, devices broadcasting their UDP beacon on the same network segment will appear
automatically in the **Discovered** list (you can disable this in the integration's options if it
conflicts with other software on your host).

## Manual installation

Copy `custom_components/pixelblaze/` into your Home Assistant `config/custom_components/` directory,
restart Home Assistant, and add the integration via the UI.

## Configuration options

After setup, click **Configure** on the Pixelblaze entry to adjust:

- **Polling interval** — seconds between coordinator polls. Default 10. Lower values are more
  responsive but use more bandwidth.
- **Disable UDP auto-discovery** — turn off the beacon listener for this Home Assistant instance.
  Useful if port 1889 is already used by another tool on your host.

## Example automations

Activate a specific pattern at sunset:

```yaml
automation:
  - alias: "Pixelblaze sunset"
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: pixelblaze.set_pattern
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          # Use the exact label from the pattern picker, including any "(idprefix)"
          # suffix when names collide. Pattern ids also work.
          pattern: "Slow Color"
```

Tweak a pattern's exported variable from a script:

```yaml
script:
  faster:
    sequence:
      - action: pixelblaze.set_variable
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          name: speed
          value: 0.9   # numeric only — strings and booleans are rejected
```

Activate a full scene (pattern + brightness + variables) in one shot, avoiding the
intermediate flicker you'd get from chaining three calls:

```yaml
script:
  movie_mode:
    sequence:
      - action: pixelblaze.activate_scene
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          pattern: "Slow Color"
          brightness: 0.25
          variables:
            speed: 0.2
            saturation: 1.0
```

Read the active pattern's exported variables for use in templating:

```yaml
script:
  read_speed:
    sequence:
      - action: pixelblaze.get_variables
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
        response_variable: pb
      # pb.devices is a mapping: { "<device_id>": { "speed": 0.4, ... } }
      - variables:
          speed: "{{ pb.devices.values() | first | default({}) | get('speed', 0) }}"
```

## Troubleshooting

- **"Cannot connect"**: Pixelblaze must be reachable on its websocket (port 81). Open the
  device's web UI in a browser to verify.
- **Auto-discovery never sees a device**: HAOS uses host networking, which works. Docker bridge
  networking blocks UDP broadcasts — use manual setup instead.
- **Port 1889 conflict**: another tool on the host (e.g., the Pixelblaze desktop firmware
  updater) is already listening. Disable the beacon listener in the integration's options; HACS
  setup and DHCP discovery still work.
- **Pattern list is stale**: call the `pixelblaze.refresh_pattern_list` service after editing a
  pattern via the device's web UI.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- ElectroMage for [Pixelblaze](https://www.bhencke.com/pixelblaze).
- [@zranger1](https://github.com/zranger1) for the [`pixelblaze-client`](https://github.com/zranger1/pixelblaze-client)
  library this integration is built on.

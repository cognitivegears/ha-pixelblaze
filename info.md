# Pixelblaze for Home Assistant

A full-coverage Home Assistant custom integration for [Pixelblaze](https://www.bhencke.com/pixelblaze)
WiFi LED controllers.

- **UI setup** — no YAML required.
- **Auto-discovery** via DHCP and a defensive UDP beacon listener.
- **Entities**: `light` (brightness + effect), `select` (pattern + sequencer mode),
  dynamic `number` per active-pattern slider, `switch`, `sensor`, `button`, `update`.
- **Custom services**: `set_variable`, `set_pattern`, `next_pattern`, `set_sequencer_mode`,
  `set_color_control`, and more.

After installing via HACS, restart Home Assistant and add the integration from
**Settings → Devices & Services**.

See the [README](https://github.com/cognitivegears/ha-pixelblaze#readme) for the full feature
matrix and known limitations.

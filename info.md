# Pixelblaze for Home Assistant

Native Home Assistant control for [Pixelblaze](https://www.bhencke.com/pixelblaze) WiFi LED controllers.

- **Lights** — brightness, on/off, and patterns as effects
- **Color pickers** — every `hsvPicker*` control on the active pattern surfaces as its own HS-color light
- **Sliders** — every `slider*` control surfaces as a `number` entity
- **Pattern + sequencer selects, switches, sensors, buttons, firmware update entity**
- **Scenes in one call** — `pixelblaze.activate_scene` applies pattern + brightness + variables atomically
- **Auto-discovery** via DHCP and a defensive UDP beacon listener
- **Local polling** — no cloud, no account

## Setup

After install, restart Home Assistant and add the integration from **Settings → Devices & Services**.

## Documentation

See the [README](https://github.com/cognitivegears/ha-pixelblaze#readme) and the [docs/](https://github.com/cognitivegears/ha-pixelblaze/tree/main/docs) folder for the full feature reference, automation examples, troubleshooting, and known limitations.

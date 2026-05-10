# Pixelblaze for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-03A9F4.svg)](https://www.home-assistant.io)
[![Quality Scale](https://img.shields.io/badge/quality%20scale-silver-silver.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Validate](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-pixelblaze/actions/workflows/hacs.yml)

**Native Home Assistant control for [Pixelblaze](https://www.bhencke.com/pixelblaze) WiFi LED controllers.** Brightness, patterns, color pickers, per-pattern sliders, and scenes — all without YAML.

---

## Why this integration

Pixelblaze controllers are powerful, but driving them from Home Assistant has historically meant scripting against the websocket API by hand. This integration makes a Pixelblaze feel like any other first-class Home Assistant device: discovered automatically, configured in the UI, and exposed through native entities.

- **Lights** with brightness and pattern selection as effects
- **Color pickers** — every `hsvPicker*` control on the active pattern becomes its own HS-color light
- **Sliders** — every `slider*` control on the active pattern becomes a `number` entity
- **Selects** for pattern and sequencer mode, **switches**, **sensors**, **buttons**, and a firmware **update** entity
- **Scenes in one call** — `pixelblaze.activate_scene` applies pattern + brightness + variables atomically (no flicker)
- **Auto-discovery** via DHCP and a defensive UDP beacon listener
- **Local polling** — no cloud, no account

See [docs/features.md](docs/features.md) for the full entity and service reference.

## Getting started

### 1. Install via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cognitivegears&repository=ha-pixelblaze&category=integration)

Click the badge above, or add it manually:

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/cognitivegears/ha-pixelblaze` with category **Integration**.
3. Search for **Pixelblaze** and install.
4. Restart Home Assistant.

> Don't have HACS yet? Follow the [HACS install guide](https://hacs.xyz/docs/setup/download), then come back.

### 2. Add your Pixelblaze

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pixelblaze)

Or manually: **Settings → Devices & Services → Add Integration → Pixelblaze**, and enter the device's IP or hostname.

Devices on the same network segment will also appear in the **Discovered** list automatically.

### 3. Use it

Your Pixelblaze appears as a device with a light, pattern selector, and a set of dynamic controls that change with the active pattern. Drop it on a dashboard, control it from a voice assistant, or wire it into automations.

```yaml
# Activate a scene at sunset — pattern, brightness, and variables in one atomic call.
automation:
  - alias: "Pixelblaze sunset"
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: pixelblaze.activate_scene
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          pattern: "Slow Color"
          brightness: 0.25
          variables:
            speed: 0.2
```

More examples in [docs/automations.md](docs/automations.md).

## Requirements

- Home Assistant **2025.1.0** or later
- A Pixelblaze reachable on your local network (websocket port 81)

## Documentation

| Topic | Details |
| --- | --- |
| [Features](docs/features.md) | Full entity and service reference |
| [Configuration](docs/configuration.md) | Options after install |
| [Automations](docs/automations.md) | Example YAML for common tasks |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |
| [Limitations](docs/limitations.md) | What's intentionally not supported |
| [Manual install](docs/manual-install.md) | For users not running HACS |
| [Contributing](CONTRIBUTING.md) | Developer setup and guidelines |
| [Changelog](CHANGELOG.md) | Release notes |
| [Security](SECURITY.md) | Reporting vulnerabilities |

## License

[MIT](LICENSE) — built on [`pixelblaze-client`](https://github.com/zranger1/pixelblaze-client) by [@zranger1](https://github.com/zranger1). Pixelblaze hardware and firmware © [ElectroMage](https://www.bhencke.com/pixelblaze).

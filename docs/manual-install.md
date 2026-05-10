# Manual install

If you don't use HACS, you can install the integration by hand.

1. Download or clone this repository.
2. Copy `custom_components/pixelblaze/` into your Home Assistant `config/custom_components/` directory. The result should be `config/custom_components/pixelblaze/manifest.json`.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add Integration → Pixelblaze**.

To update, replace the `pixelblaze` directory with the new release and restart.

## Why HACS is recommended

HACS handles updates and version pinning for you, surfaces release notes in the Home Assistant UI, and is the standard distribution channel for community integrations. Manual install is supported but you'll need to track new versions yourself.

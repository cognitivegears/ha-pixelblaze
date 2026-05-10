# Troubleshooting

## "Cannot connect"

The Pixelblaze must be reachable on its websocket (port 81). Open the device's web UI in a browser to confirm — if that works, Home Assistant should be able to connect from the same network.

## Auto-discovery never sees a device

- **HAOS** uses host networking — UDP broadcasts work and discovery should find devices automatically.
- **Docker bridge networking** blocks UDP broadcasts. Use manual setup (enter the IP/hostname) or switch the container to host networking.

## Port 1889 conflict

Another tool on the host (e.g., the Pixelblaze desktop firmware updater) is already listening on UDP 1889. Disable the beacon listener in the integration's options — HACS setup and DHCP discovery still work.

## Pattern list is stale

Call the `pixelblaze.refresh_pattern_list` service after editing a pattern via the device's web UI.

## Pattern name collisions

When two patterns on the device share a name, the integration appends a 6-character id prefix to disambiguate, e.g. `Sparkles (KGksY)`. Automations targeting patterns by name must use this exact label, or pass the pattern id directly. Pattern ids are visible via diagnostics and in the `pixelblaze.set_pattern` service trace.

## Reporting issues

Please include:

- Home Assistant version
- Integration version (from `manifest.json`)
- Pixelblaze firmware version (from the **Firmware version** sensor)
- Relevant log output from `homeassistant.components.pixelblaze` and `custom_components.pixelblaze`

Open issues at <https://github.com/cognitivegears/ha-pixelblaze/issues>.

# Configuration

After install, click **Configure** on the Pixelblaze entry in **Settings → Devices & Services** to adjust:

| Option | Default | Notes |
| --- | --- | --- |
| Polling interval | 10 s | Seconds between coordinator polls. Lower values are more responsive but use more bandwidth. |
| Disable UDP auto-discovery | off | Turns off the beacon listener for this Home Assistant instance. Useful if port 1889 is already used by another tool on your host. |

Saving the options form without changing any values does not trigger an entity reload.

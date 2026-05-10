# Claude development notes

This file is a quick orientation for AI assistants (and humans) working in the repo.

## Layout

- `custom_components/pixelblaze/` — the Home Assistant integration.
- `tests/` — pytest suite. Stubs `pixelblaze` at import time so tests don't need real hardware.
- `scripts/` — `check_requirements_sync.py`, `sync_manifest_requirements.py` keep the
  `manifest.json` `requirements` field aligned with `pyproject.toml` pins.
- `.github/workflows/` — `validate` (lint+test), `hassfest`, `hacs`, `security`, `dependabot-auto-sync`.

## Architecture

- The upstream `pixelblaze-client` library is **synchronous** (`websocket-client` based). The
  `api.PixelblazeClient` wraps every call through `hass.async_add_executor_job` and serializes
  websocket calls per device with an `asyncio.Lock`.
- A `DataUpdateCoordinator` (`coordinator.py`) polls the device every 10 s by default. State is
  exposed as `PixelblazeState` (a dataclass) and consumed by all platforms.
- `entry.runtime_data: PixelblazeRuntimeData` holds `(client, coordinator)`. We do **not** use
  `hass.data[DOMAIN]` for per-entry state.
- Discovery: `discovery.py` runs a single UDP listener on port 1889 (with `SO_REUSEADDR`,
  defensive `OSError` handling, and TTL-based dedup). Each new device is dispatched as
  `SOURCE_INTEGRATION_DISCOVERY` to the config flow.

## Avoid mini-racer paths

`pixelblaze-client` ships `mini-racer` (V8) as a transitive dep for pattern decompilation /
compilation. We deliberately avoid every method that exercises it: `getPatternAsObject`,
`savePattern`, EPE pack/unpack. The README documents what's deferred to a future release.

## Testing

```bash
pytest -q                              # unit tests (default)
pytest -m integration                  # integration tests against real hardware
ruff check custom_components tests scripts
mypy custom_components
```

The `FakePixelblaze` class in `tests/conftest.py` is the canonical stub — extend it when adding
new methods to `PixelblazeClient`.

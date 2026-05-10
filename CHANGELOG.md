# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.5] - 2026-05-10

### Fixed

- Already-configured devices no longer reappear under "Discovered" in the
  integrations list. The user flow stored the raw hex `pixelblazeId` as the
  config-entry unique_id while UDP-beacon discovery emitted `pb:xxxxxxxx`,
  so `_abort_if_unique_id_configured` never matched. Both paths now produce
  a canonical `pb:xxxxxxxx` id, and existing entries are migrated on load.

### Changed

- Bumped `hacs.json` `homeassistant` minimum from `2025.1.0` to `2026.2.0` to
  match the actual floor implied by `requires-python = ">=3.13.2"` (Home
  Assistant 2026.2 is the first release shipping Python 3.14). Prep for HACS
  default-repository submission.

## [0.2.4] - 2026-05-10

### Fixed

- Capped `requires-python` at `<3.15` in `pyproject.toml` so Dependabot's uv
  resolver no longer fails with a "no solution found" error when splitting
  on `python_full_version >= '3.15'`. Home Assistant currently requires
  Python 3.14.2 and does not yet support 3.15; the lower bound stays at
  3.13.2 so the integration still installs into HA 2026.2.x.

## [0.2.3] - 2026-05-10

### Changed

- Per-pattern slider `number` entities are now primary entities (previously
  `EntityCategory.CONFIG`). They are runtime user controls, not settings, so
  they now appear in the auto-generated device card by default.

### Added

- `docs/dashboard.md` — guide to building a Pixelblaze dashboard, with
  copy-pasteable Lovelace YAML for entities cards, light cards with the
  effect/pattern picker, tile cards, scene buttons (`activate_scene`), and
  per-pattern button grids.
- README links to the new dashboard guide.

## [0.2.2] - 2026-05-10

No code changes — documentation overhaul.

### Changed

- Rewrote `README.md` to lead with the value proposition, a one-click HACS
  install badge, a one-click "add integration" badge, and a three-step
  Getting Started section. Detail moved to `docs/`.
- Added shields for HACS, Home Assistant version, quality scale, and license.
- Updated `info.md` (rendered by HACS in the HA UI) to mirror the new README.

### Added

- `docs/features.md` — full entity and service reference plus discovery and
  diagnostics notes.
- `docs/configuration.md` — options reference.
- `docs/automations.md` — example YAML for common tasks.
- `docs/troubleshooting.md` — connection, discovery, port-conflict, and
  pattern-collision guidance plus issue-reporting checklist.
- `docs/limitations.md` — intentional v1 cuts, runtime caveats, and the
  feature matrix.
- `docs/manual-install.md` — non-HACS install steps.

## [0.2.1] - 2026-05-10

No user-facing changes — CI and developer-tooling cleanup.

### Changed

- CI workflows (`validate.yml`, `security.yml`) now install pinned dev tools
  via `pip install -e ".[dev|security]"` instead of pulling unpinned
  `ruff`/`mypy`/`bandit` from PyPI. The previous unpinned install was
  picking up newer ruff releases whose added rules (FURB110, UP047)
  weren't enforced by the version pinned in `pyproject.toml`, breaking
  `main` on every push.
- Bumped dev dependencies (Python 3.13 / HA <2026.4 compatible):
  `ruff` 0.15.1→0.15.12, `mypy` 1.19.1→2.0.0, `bandit` 1.9.3→1.9.4,
  `pre-commit` 4.5.1→4.6.0, `pytest-homeassistant-custom-component`
  0.13.314→0.13.316.
- `actions/github-script` v8→v9 in the HACS workflow.
- Repo metadata: added the HACS-required topics (`hacs`, `home-assistant`,
  `integration`, `custom-component`, `pixelblaze`, `leds`, `ws2812`,
  `led-strip`).

### Fixed

- Lint issues introduced by ruff 0.15.12: replaced a redundant ternary
  with `or`, and converted `_safe_get` to PEP 695 generic-function
  syntax (dropping the now-unused `TypeVar`).

### Notes

- `pytest` 9.0.0→9.0.3 (CVE-2025-71176) cannot be applied yet:
  `pytest-homeassistant-custom-component` 0.13.316 — the latest release
  that still supports Python 3.13, which Home Assistant uses through
  2026.3 — hard-pins `pytest==9.0.0` and `pytest-cov==7.0.0`. Versions
  0.13.317+ require Python 3.14. The Dependabot alert was dismissed as
  *tolerable risk*: `pytest` is a CI-only dev dep, not shipped to users,
  and the vulnerability requires local access to the runner's `/tmp`.
  Will revisit when we bump the integration's Python requirement to
  3.14.

## [0.2.0] - 2026-05-10

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

### Fixed

- Quoted `"off"` in the `services.yaml` `select` selectors for
  `set_sequencer_mode` and `activate_scene`. YAML 1.1 parses bare `off` as
  the boolean `False`, which failed HA's selector schema and caused HA to
  discard the entire `services.yaml` — so no Pixelblaze action showed any
  input fields in the automation editor.
- 500 error when opening the config flow.

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

[Unreleased]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/cognitivegears/ha-pixelblaze/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/cognitivegears/ha-pixelblaze/releases/tag/v0.1.0

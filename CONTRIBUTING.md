# Contributing to ha-pixelblaze

Thanks for your interest in contributing! This document covers the developer setup and the
expectations for changes.

## Local development

```bash
# Python 3.13.2 is required (tracked in .python-version).
uv sync --all-extras           # or: pip install -e ".[dev]"
pre-commit install
```

## Running checks

```bash
uv run ruff check custom_components tests scripts
uv run mypy custom_components
uv run pytest -q
```

The dependency-sync hook ensures `manifest.json` requirements stay aligned with
`pyproject.toml`/`uv.lock`. To rewrite the manifest after a dependency change:

```bash
python scripts/sync_manifest_requirements.py        # rewrites manifest
python scripts/check_requirements_sync.py           # verifies it
```

## Making changes

- Branch from `main`.
- Keep PRs focused — one logical change per PR.
- New entities or services require accompanying tests under `tests/`. Coverage is enforced
  (`fail_under = 80.0` in `pyproject.toml`).
- Update `strings.json` and `translations/en.json` when adding new user-facing strings.
- Update the README "What's included / not" matrix if you ship new platform support or remove
  features.
- Avoid the `mini-racer` code paths in `pixelblaze-client` — pattern source decompilation,
  upload, and EPE are deliberately out of scope for v1.0.

## Testing strategy

Tests are split into:

- **Unit tests** (default): the `pixelblaze` module is stubbed in `tests/conftest.py` so tests
  run without hardware. These are what CI runs.
- **Integration tests** (`@pytest.mark.integration`): exercised against a real Pixelblaze.
  Excluded by default; run with `pytest -m integration`.

When adding tests, prefer unit tests with the `FakePixelblaze` stub. Reach for integration tests
only for behavior that depends on real device timing.

## Reporting issues

Please include:

- Home Assistant version
- Integration version (from `manifest.json`)
- Pixelblaze firmware version (from the **Firmware version** sensor)
- Relevant log output from `homeassistant.components.pixelblaze` and
  `custom_components.pixelblaze`

## Code of conduct

Be kind. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

# Security policy

## Supported versions

Only the latest released version of `ha-pixelblaze` receives security fixes. We follow Home
Assistant's monthly release cadence and aim to ship integration patches within a release of
an upstream advisory in `pixelblaze-client` or its transitive dependencies.

## Reporting a vulnerability

**Please do not file public issues for security-impacting bugs.** Open a private security
advisory using GitHub's [Report a vulnerability](https://github.com/cognitivegears/ha-pixelblaze/security/advisories/new)
form on this repository. We monitor that channel; it provides controlled disclosure with
the maintainers before any public discussion.

When reporting, please include:

- Version of `ha-pixelblaze`, Home Assistant, and Pixelblaze firmware.
- Network setup (HAOS / supervised / Docker, networking mode, isolation between Pixelblaze
  and other devices).
- Steps to reproduce, or a proof-of-concept payload. Beacon-related issues should include
  the raw UDP packet bytes if relevant.
- Observed behavior vs expected behavior.

We aim to triage within a week and to ship a fix or mitigation within one Home Assistant
monthly release of confirming the issue.

## Threat model

This integration is designed for use on **trusted local networks**. Pixelblaze devices have
no authentication on their websocket (port 81) or HTTP endpoints, so anyone with network
access to the device can control it. Home Assistant exposes the same level of control via
the entities and services this integration provides.

The UDP beacon listener (port 1889) accepts broadcast packets from the local segment only
and applies several defensive measures:

- Token-bucket rate limit (50 packets/sec).
- Packet length cap (≤ 256 bytes).
- Optional name field is length-capped (64 chars), invalid UTF-8 rejected, and control
  characters / ANSI escapes / bidirectional-override codepoints stripped to prevent
  log-injection or terminal-rewrite attacks against operators viewing logs.
- Dedup map bounded at 1024 entries with TTL-based eviction.

The config-flow host validator rejects link-local, loopback, multicast, and unspecified IP
addresses, scheme-prefixed URLs, paths, and strings containing whitespace. Only bare
IPv4/IPv6 literals and RFC-valid DNS hostnames are accepted.

Diagnostic exports redact (see `diagnostics.py`):

- The entry **title** (unconditional — operator-chosen and frequently personal: "Sarah's
  Birthday Lights", "Kid's Room").
- Network identifiers: `host`, `ip`.
- Device identifiers: `pixelblaze_id`, device `name`.
- Pattern catalog: `pattern_list`, `pattern_label_to_id`, `active_pattern_name`.
- Active state with potentially user-named keys: `active_controls`, `active_variables`.
- Playlist data: `playlist_id`, `playlist_items`.

Counts and shapes are preserved (e.g. `pattern_count`, `active_control_keys`) so debugging
remains possible without leaking content.

The integration does not store credentials, perform outbound calls to third-party services,
or execute pattern code locally.

## Dependencies

Security scans (Bandit for static analysis, pip-audit for dependency CVEs) run on every
push and weekly on a schedule via the `Security` workflow. Dependency updates are managed
by Dependabot.

The `pixelblaze-client` library pulls `mini-racer` (a V8 JavaScript engine) as a
transitive dependency. This integration does not invoke any V8-using code path, so the
dep is unused at runtime; it is present only to satisfy `pixelblaze-client`'s own
imports. If a vulnerability is identified in `mini-racer` we will track it and report on
mitigation status.

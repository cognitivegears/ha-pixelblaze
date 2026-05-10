# Building a Pixelblaze dashboard

The integration creates more entities than the auto-generated device card surfaces. This guide shows how to wire them into a real dashboard.

> Replace `<device>` in the entity IDs below with your Pixelblaze's slug (the device name lowercased with spaces → underscores), e.g. `lobby_pixelblaze`.

## Entities at a glance

| Entity | Default visibility | Purpose |
| --- | --- | --- |
| `light.<device>` | Primary | Brightness, on/off, **and pattern as an effect** |
| `select.<device>_pattern` | Primary | Pick the active pattern by name |
| `light.<device>_<hsvpicker>` | Primary, per pattern | Color picker controls — appear/disappear with the active pattern |
| `number.<device>_<slider>` | Primary, per pattern | Pattern slider controls — appear/disappear with the active pattern |
| `select.<device>_sequencer_mode` | Configuration | Off / Shuffle / Playlist |
| `switch.<device>_sequencer` | Configuration | Quick on/off for shuffle |
| `button.<device>_next_pattern` | Primary | Advance one pattern |
| `button.<device>_reboot` | Configuration | Reboot the controller |
| `sensor.<device>_fps` | Primary | Render rate |
| `sensor.<device>_uptime` / `_firmware_version` / `_ip` / `_led_count` / `_storage_*` | Diagnostic | Device info |
| `update.<device>_firmware` | Configuration | Read-only firmware version |

> **Tip — the Light card already has a pattern picker.** On the default Light card, click the gear and enable **"Show effect picker"** (or in YAML add `show_effect_picker: true`). Effects are mapped 1:1 to your patterns.

## Recipe 1 — Quick controls (Entities card)

Drops the most common controls into a compact card.

```yaml
type: entities
title: Lobby Pixelblaze
entities:
  - entity: light.lobby_pixelblaze
    name: Lights
  - entity: select.lobby_pixelblaze_pattern
    name: Pattern
  - entity: button.lobby_pixelblaze_next_pattern
    name: Next pattern
  - entity: switch.lobby_pixelblaze_sequencer
    name: Shuffle
  - entity: select.lobby_pixelblaze_sequencer_mode
    name: Sequencer mode
  - entity: sensor.lobby_pixelblaze_fps
    name: FPS
```

## Recipe 2 — Light card with pattern picker

The built-in Light card shows brightness, on/off, *and* a pattern picker via the effect dropdown.

```yaml
type: light
entity: light.lobby_pixelblaze
name: Lobby Pixelblaze
show_effect_picker: true
```

## Recipe 3 — Tiles for fast access

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: light.lobby_pixelblaze
    features:
      - type: light-brightness
  - type: tile
    entity: select.lobby_pixelblaze_pattern
    features:
      - type: select-options
  - type: horizontal-stack
    cards:
      - type: tile
        entity: button.lobby_pixelblaze_next_pattern
      - type: tile
        entity: switch.lobby_pixelblaze_sequencer
```

## Recipe 4 — Pattern controls (color + sliders)

The active pattern's controls appear dynamically. Both color pickers and slider numbers are primary entities, so the auto-generated device card shows them. To pull them onto a custom card, reference them by entity ID — replace the IDs below with whatever your active pattern exposes (open the device page in Home Assistant to see them).

```yaml
type: entities
title: Pattern controls
entities:
  - entity: light.lobby_pixelblaze_hsvpickercolor      # color picker
    name: Color
  - entity: number.lobby_pixelblaze_slidersize        # any slider name
    name: Size
  - entity: number.lobby_pixelblaze_sliderspeed
    name: Speed
state_color: true
```

Color pickers render as full HS-color lights, so you get a real swatch and brightness slider for each one.

## Recipe 5 — Scene buttons (one click = full look)

`pixelblaze.activate_scene` applies pattern + brightness + variables atomically — perfect for buttons. Define scripts first, then wire them to button cards.

```yaml
# scripts.yaml
movie_mode:
  alias: Pixelblaze movie mode
  sequence:
    - action: pixelblaze.activate_scene
      data:
        device_id: "{{ device_id('Lobby Pixelblaze') }}"
        pattern: "Slow Color"
        brightness: 0.25
        variables:
          speed: 0.2

party_mode:
  alias: Pixelblaze party mode
  sequence:
    - action: pixelblaze.activate_scene
      data:
        device_id: "{{ device_id('Lobby Pixelblaze') }}"
        pattern: "Sparkles"
        brightness: 1.0
        variables:
          speed: 0.9
```

```yaml
# dashboard
type: horizontal-stack
cards:
  - type: button
    name: Movie
    icon: mdi:movie
    tap_action:
      action: perform-action
      perform_action: script.movie_mode
  - type: button
    name: Party
    icon: mdi:party-popper
    tap_action:
      action: perform-action
      perform_action: script.party_mode
```

## Recipe 6 — Pattern picker as a button grid

If you want one tap per favorite pattern, drop a row of buttons that each call `pixelblaze.set_pattern`.

```yaml
type: grid
columns: 3
square: false
cards:
  - type: button
    name: Slow Color
    tap_action:
      action: perform-action
      perform_action: pixelblaze.set_pattern
      data:
        device_id: "{{ device_id('Lobby Pixelblaze') }}"
        pattern: "Slow Color"
  - type: button
    name: Sparkles
    tap_action:
      action: perform-action
      perform_action: pixelblaze.set_pattern
      data:
        device_id: "{{ device_id('Lobby Pixelblaze') }}"
        pattern: "Sparkles"
  - type: button
    name: KITT
    tap_action:
      action: perform-action
      perform_action: pixelblaze.set_pattern
      data:
        device_id: "{{ device_id('Lobby Pixelblaze') }}"
        pattern: "KITT"
```

## Why don't I see all of these on the auto-generated card?

Home Assistant categorizes entities as **Primary**, **Configuration**, or **Diagnostic**. The default Tile card on a device page only shows primary entities. Configuration and diagnostic entities are reachable from the device's full entity list (the "Configuration" / "Diagnostic" sections on the device page) and from any card that references them by entity ID.

Pattern sliders and color pickers are primary entities, so they appear by default. The sequencer mode/switch and reboot button are filed as Configuration since they're settings, not regular controls — reference them by entity ID if you want them on a card.

# Example automations

## Activate a pattern at sunset

```yaml
automation:
  - alias: "Pixelblaze sunset"
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: pixelblaze.set_pattern
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          # Use the exact label from the pattern picker, including any "(idprefix)"
          # suffix when names collide. Pattern ids also work.
          pattern: "Slow Color"
```

## Tweak an exported pattern variable

```yaml
script:
  faster:
    sequence:
      - action: pixelblaze.set_variable
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          name: speed
          value: 0.9   # numeric only — strings and booleans are rejected
```

## Activate a full scene atomically

`activate_scene` applies pattern + brightness + variables + sequencer mode under a single per-device lock and emits one optimistic state patch — no flicker from chaining multiple calls.

```yaml
script:
  movie_mode:
    sequence:
      - action: pixelblaze.activate_scene
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
          pattern: "Slow Color"
          brightness: 0.25
          variables:
            speed: 0.2
            saturation: 1.0
```

## Read variables for templating

```yaml
script:
  read_speed:
    sequence:
      - action: pixelblaze.get_variables
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
        response_variable: pb
      # pb.devices is a mapping: { "<device_id>": { "speed": 0.4, ... } }
      - variables:
          speed: "{{ pb.devices.values() | first | default({}) | get('speed', 0) }}"
```

## Refresh the pattern list after editing patterns on the device

```yaml
script:
  refresh_patterns:
    sequence:
      - action: pixelblaze.refresh_pattern_list
        data:
          device_id: "{{ device_id('Lobby Pixelblaze') }}"
```

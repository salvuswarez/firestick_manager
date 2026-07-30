---
name: devices-config
description: resources/devices.yml schema and how device_store.py reads/writes it. Use when adding/editing devices or debugging why a device isn't picked up by --batch.
---

# devices.yml Configuration Reference

`resources/devices.yml` is the fleet inventory. `fire_tools.device_store.DeviceStore` (backed by the `fire_tools.models.Device` pydantic model) both writes it (from `scan`) and reads it (`maintain --batch`, `deploy --batch`). `resources/devices.yml.example` is the tracked reference for this schema — copy it to `devices.yml` (gitignored — real MAC/IP data) to get started, or just run `scan`.

## Schema

```yaml
devices:
  - ip: 192.168.1.50
    mac: aa:bb:cc:dd:ee:ff
    name: Example Fire TV
    model: Unknown          # written by scan (ADB getprop ro.product.model)
    serial: ""              # written by scan (ADB getprop ro.serialno)
    android_version: ""     # written by scan
    display: {}             # never written by scan — hand-add resolution_index/overscan here
```

`scan` writes `ip`/`mac`/`name`/`model`/`serial`/`android_version` (via `fire_tools.jobs.scan.run_scan` -> `fire_tools._merge.reconcile`, matching existing devices by MAC, then serial, then IP). `display` is never populated by `scan` — hand-add `resolution_index`/`overscan` keys there for a device that needs `apply-display` calibration (`fire_tools.jobs.display.run_apply_display`).

## How the CLI uses it

`cli.py`'s `--batch` flag on `maintain`/`deploy` calls `DeviceStore(...).list()` and iterates every device's `ip`. A non-batch invocation just uses the CLI-provided `ip` directly — it doesn't need to be in `devices.yml` at all for `maintain`/`capture`/`deploy`.

## Gotchas

- If a device's IP changes (DHCP lease renewal, router reboot), `devices.yml` goes stale silently — nothing detects this automatically. Re-run `/fire-scan` or `uv run fire-tools scan` periodically, especially before a `--batch` operation.
- `scan` reconciles by MAC first, so a device keeps its identity (and any hand-added `display` settings) across IP changes — as long as the MAC is resolvable via ARP (same-subnet devices only).
- Per-device `display` settings only apply via `apply-display` — they have no effect on `maintain`/`deploy`.

## Argument: $ARGUMENTS

If asked to add/update a device, edit `resources/devices.yml` directly (it's plain YAML, no schema validation) rather than hand-writing Python.

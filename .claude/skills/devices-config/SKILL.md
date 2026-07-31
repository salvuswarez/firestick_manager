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
    display:                # written by capture (reads live guisettings.xml)
      resolution_index: 16
      overscan: {left: 0, top: 0, right: 1920, bottom: 1080}
```

`scan` writes `ip`/`mac`/`name`/`model`/`serial`/`android_version` (via `fire_tools.jobs.scan.run_scan` -> `fire_tools._merge.reconcile`, matching existing devices by MAC, then serial, then IP). `display` is populated by `capture` instead: `fire_tools._kodi.collect_kodi_display_settings` reads the device's live `guisettings.xml` (`videoscreen.resolution` setting + first `<resolutions>` block's overscan) and `fire_tools.device_store.DeviceStore.update_display` writes it into the matching device — replacing whatever was stored before, since it reflects a live read. `resolution_index`/`overscan` are also hand-editable to pre-seed a device before its first capture, or to force a specific value.

## How the CLI uses it

`cli.py`'s `--batch` flag on `maintain`/`deploy` calls `DeviceStore(...).list()` and iterates every device's `ip`. A non-batch invocation just uses the CLI-provided `ip` directly — it doesn't need to be in `devices.yml` at all for `maintain`/`capture`/`deploy`.

## Gotchas

- If a device's IP changes (DHCP lease renewal, router reboot), `devices.yml` goes stale silently — nothing detects this automatically. Re-run `/fire-scan` or `uv run fire-tools scan` periodically, especially before a `--batch` operation.
- `scan` reconciles by MAC first, so a device keeps its identity (and any stored `display` settings) across IP changes — as long as the MAC is resolvable via ARP (same-subnet devices only).
- `capture` only records `display` if it actually finds a value in `guisettings.xml` — Kodi omits a setting from that file entirely when it's still at default, so a device that's never been manually calibrated legitimately captures an empty `display` (not an error). `update_display` no-ops (doesn't blank out a prior value) when nothing was found that run.
- `deploy` reapplies a device's stored `display` automatically after syncing config — a hand-edited or malformed entry is logged and skipped (deploy still completes) rather than failing the whole run. Use `apply-display` for a one-off calibration outside of a deploy.

## Argument: $ARGUMENTS

If asked to add/update a device, edit `resources/devices.yml` directly (it's plain YAML, no schema validation) rather than hand-writing Python.

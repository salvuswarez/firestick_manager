---
name: devices-config
description: resources/devices.yml schema and how glossary.py reads it (get_target_ips vs get_device_configs, DEFAULT_IPS fallback). Use when adding/editing devices or debugging why a device isn't picked up by --batch.
---

# devices.yml Configuration Reference

`resources/devices.yml` is the fleet inventory — the single file both `scanner.py` (writer) and `glossary.py` (reader) agree on.

## Schema

```yaml
devices:
  - ip: 192.168.1.50
    mac: aa:bb:cc:dd:ee:ff
    name: Example Fire TV
    resolution: "1920x1080"   # optional, only used by deploy
```

`scan` writes `ip`/`mac`/`name` (no `resolution` — that field is only ever hand-added, `scanner.py` never sets it).

## Reader Functions (`glossary.py`)

| Function | Returns | Fallback if `devices.yml` is missing/empty |
|----------|---------|----------------------------------------------|
| `get_target_ips()` | `list[str]` of IPs only | `DEFAULT_IPS` (4 hardcoded IPs) |
| `get_device_configs()` | `list[dict]` — full device dicts including `resolution` | `[{"ip": ip, "resolution": "1920x1080"} for ip in DEFAULT_IPS]` |

`cli.py`'s `--batch` flag on `maintain`/`deploy` calls `get_device_configs()`. Non-batch invocations build a single-device dict inline from the CLI-provided IP (with `resolution: None` for `deploy`).

## Gotchas

- `DEFAULT_IPS` in `glossary.py` and the hardcoded `FIRE_STICKS` list in the legacy root `kodi_deployment.py` are **different lists** — don't assume they're kept in sync.
- If a device's IP changes (DHCP lease renewal, router reboot), `devices.yml` goes stale silently — nothing detects this automatically. Re-run `/fire-scan` or `uv run fire-tools scan` periodically, especially before a `--batch` operation.
- Per-device `resolution` only affects the Kodi deploy path (`KodiManager.apply_display_fixes` / the resolution arg threaded through `deploy_config`) — it has no effect on `maintain`.

## Argument: $ARGUMENTS

If asked to add/update a device, edit `resources/devices.yml` directly (it's plain YAML, no schema validation) rather than hand-writing Python.

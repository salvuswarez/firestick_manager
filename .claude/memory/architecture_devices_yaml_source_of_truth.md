---
name: devices.yml as fleet source of truth
description: resources/devices.yml is the single inventory both scanner.py (writer) and glossary.py (reader) agree on.
type: project
---

`scanner.py`'s `scan_and_save()` writes `resources/devices.yml`; `glossary.py`'s `get_target_ips()`/`get_device_configs()` read it, falling back to hardcoded `DEFAULT_IPS` only if the file is absent. `cli.py`'s `--batch` flag on `maintain`/`deploy` is entirely driven by this file.

**Why:** Avoids hardcoding IPs in multiple places; scanning is the intended way to keep the fleet list current as DHCP leases change.

**How to apply:** Prefer re-running `/fire-scan` over hand-editing IPs when a device seems unreachable. Hand-edit only to add the `resolution` field, which `scanner.py` never writes.

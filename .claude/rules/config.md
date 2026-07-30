---
paths: ["src/fire_tools/glossary.py", "resources/**"]
---

# Config & Glossary Rules

When working in `glossary.py` or `resources/`:

1. **`devices.yml` is data, not code** — validate IPs/structure before writing, don't hand-edit `DEFAULT_IPS` in `glossary.py` as a substitute for updating the YAML.
2. **New bloat packages go in `BLOAT_PACKAGES`**, never inline in `core.py` — keep the debloat list centralized.
3. **New junk paths go in `JUNK_PATHS`**, addon exceptions in `WHITELIST_ADDONS`/`REQUIRED_PREFIXES` — see the `kodi-gold-config` skill before changing pruning behavior.
4. **Constants here are read at import time** (`STICK_IPS = get_target_ips()`) — a change to `devices.yml` mid-process won't be picked up without re-importing; this matters for long-running batch operations.

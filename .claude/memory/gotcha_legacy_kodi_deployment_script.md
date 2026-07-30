---
name: legacy kodi_deployment.py
description: Root-level kodi_deployment.py predates/duplicates src/fire_tools/core.py and is not part of the installed package.
type: project
---

`kodi_deployment.py` at the repo root has its own `FIRE_STICKS` hardcoded IP list, `debloat_device`, `re_enable_bloatware` (a debloat-restore path that has no equivalent in `core.py`), and `find_kodi_paths`. It's not referenced by `pyproject.toml`'s package list or entry point, and isn't imported by anything in `src/fire_tools/`.

**Why:** Looks like the original prototype before the `fire_tools` package existed.

**How to apply:** Don't edit this file expecting it to affect the real CLI — check `src/fire_tools/core.py` instead. If the user wants bloat-restore functionality, port `re_enable_bloatware` into `Firestick` rather than resurrecting this script. Flag it as a deletion candidate if asked to clean up the repo.

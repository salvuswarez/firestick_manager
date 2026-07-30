---
name: capture never prunes, prep is opt-in
description: capture_gold_image never deletes/overwrites; _prep_local_config only runs when deploy is passed --prep.
type: project
---

`KodiManager.capture_gold_image()` always creates a new `.kodi_<timestamp>` folder — disk usage in `assets/`/`archive/` grows unbounded, there is no auto-pruning. Separately, `_prep_local_config()` (JUNK_PATHS cleanup + addon whitelist pruning) is NOT called automatically after capture — the call exists in `core.py` but is commented out. It only runs when `deploy` is invoked with `--prep`.

**Why:** Deliberate safety choice per the docstring ("Does NOT delete or overwrite anything") — capture is meant to be a safe, repeatable snapshot operation.

**How to apply:** Don't assume a freshly-captured build is pruned. If disk usage becomes a problem, that's a feature request (auto-prune or a cleanup command), not a bug. Use `/fire-builds` to check accumulated size before assuming space is free.

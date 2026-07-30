List captured Kodi builds available locally and their approximate disk usage. No arguments.

1. Glob `assets/.kodi_*` and `archive/.kodi_*` (including any `.kodi_gold_*`-named folders).
2. For each, show the folder name, `du -sh` size, and whether it's under `assets/` (working) or `archive/` (retired/gold).
3. Identify which one `get_latest_build()` would currently pick (lexically-latest `.kodi_YYYYMMDD_HHMMSS` under `assets/`) and flag if a manually-marked gold build in `archive/` is more recent but wouldn't be auto-selected.
4. Report total disk usage across both directories — this grows unbounded since captures are never auto-pruned.

Use the `kodi-gold-config` skill for why capture/build selection works the way it does.

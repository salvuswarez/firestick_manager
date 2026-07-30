---
name: kodi-gold-config
description: The Kodi "gold config" capture → prep → deploy workflow, and the JUNK_PATHS / WHITELIST_ADDONS / REQUIRED_PREFIXES pruning semantics. Use when working with .kodi_<timestamp> builds, capturing or deploying Kodi config, or editing the addon-pruning rules in glossary.py.
---

# Kodi Gold-Config Workflow

"Gold config" is a known-good Kodi setup (skin, addons, settings) captured from a real device and redeployed to others.

## Lifecycle

```
capture <ip>  ─→  assets/.kodi_<timestamp>/   (raw pull, untouched)
                        │
                        │  deploy --prep  (optional, local-only cleanup)
                        ▼
                  _prep_local_config()        (prunes in place)
                        │
                        ▼
              deploy <ip> [--update]          (push addons/userdata/media)
```

- **Capture never destroys anything.** `KodiManager.capture_gold_image()` always creates a brand-new `assets/.kodi_<YYYYMMDD_HHMMSS>/` folder via `adb pull`. Nothing is ever overwritten by a capture.
- **Prep is opt-in and local-only.** `_prep_local_config()` only runs when `deploy` is called with `--prep`. It is NOT run automatically after capture (the call is present but commented out in `capture_gold_image`).
- **`get_latest_build()` picks the most recent build by sorting folder names** — this works only because the naming is `.kodi_YYYYMMDD_HHMMSS` (lexical sort == chronological sort). A manually-marked "gold" folder like `archive/.kodi_gold_20260410_072207/` is NOT picked up by this sort unless it's moved/renamed into the `assets/` tree with a compliant timestamp name.

## Pruning Rules (`_prep_local_config`, `glossary.py`)

Two independent passes, both looking under a captured build folder:

1. **Addon pruning** — walks `<build>/addons/`. A folder survives if it's in `WHITELIST_ADDONS` (explicit allow-list, e.g. `plugin.video.umbrella`, `skin.arctic.fuse.3`) OR its name starts with one of `REQUIRED_PREFIXES` (`script.module.`, `service.`, `metadata.`, `resource.`, `inputstream.`, etc. — protects engine/dependency addons generically). Anything else is `shutil.rmtree`'d.
2. **Junk-path cleanup** — removes each entry in `JUNK_PATHS` relative to the build root. Supports a wildcard suffix (`addons/packages/*` empties and recreates the parent dir) and otherwise removes files/dirs outright (e.g. `userdata/Database/Textures13.db`, `userdata/Thumbnails`, per-addon cache subfolders).

**When adding a new addon to the gold build**: add it to `WHITELIST_ADDONS` (exact folder name) or, if it's a dependency/engine addon, check whether an existing `REQUIRED_PREFIXES` entry already protects it before adding a new one-off whitelist entry.

**When trimming disk usage further**: add to `JUNK_PATHS`, not to the addon whitelist logic — junk paths are for cache/log/thumbnail bloat, not addon lifecycle.

## Deploy Sequence (`KodiManager.deploy_config`)

1. Device prep: `debloat()` → `optimize_system()` → `disable_telemetry()` (always runs, not gated by any flag)
2. If `install_apk=True` and `assets/latest_kodi.apk` exists: `adb install -r`
3. Resolve `get_latest_build()` under `assets/.kodi/` — bails with an error message if none found
4. Force-stop Kodi, `rm -rf` + recreate the remote `.kodi` dir
5. Push `addons/`, `userdata/`, `media/` folders individually (skips any that don't exist locally)
6. Apply per-device resolution if one was passed (see `devices-config` skill)

## Argument: $ARGUMENTS

If a build name or device IP is given, walk through that specific capture/deploy scenario. Otherwise explain the general workflow.

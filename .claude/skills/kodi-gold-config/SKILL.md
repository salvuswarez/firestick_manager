---
name: kodi-gold-config
description: The Kodi "gold config" capture → SMB → deploy workflow, plus the Arctic Fuse 3 home-UI (HomeSwitcher tabs + TMDbHelper custom nodes) schema for building out sections/genres programmatically. Use when working with captures/deploys, Kodi backups on the SMB share, or adding/editing Arctic Fuse home tabs, widgets, or TMDbHelper hubs.
---

# Kodi Gold-Config Workflow

"Gold config" is a known-good Kodi setup (skin, addons, settings) captured from a real device and redeployed to others. All of this lives under `src/fire_tools/jobs/` (`capture.py`, `deploy.py`) — there is no `core.py`/`KodiManager`/`glossary.py` anymore (that was an earlier architecture; see `architecture_job_pipeline.md` in project memory).

## Lifecycle

```
capture <ip>  ─→  tar cf + gzip on-device  ─→  verify gzip  ─→  adb pull to staging  ─→  upload to SMB
                                                                        │
deploy <ip> [--backup dev/file.tar.gz]  ─→  download from SMB  ─→  extract
    ─→  prune addons to whitelist  ─→  apply settings overrides
    ─→  sync addons/userdata/media (hash-diff, not full wipe)
```

- **No local `assets/`/`archive/` anymore.** Both jobs use a per-operation staging dir (`ws: Path`, under `~/.fire_tools/staging/`) that's cleaned up after the job — nothing is retained locally. The archive lives only on the SMB share (`SmbConfig.smb_backup_dir`, default `"backups"`; the HA integration's default is `"kodi-wan/ha_storage/backups"` — check which one your `.env`/config entry actually points at, see `const.py`'s note on this).
- **Addon pruning is back**, reintroduced 2026-07-30 in `_addon_policy.py` (`WHITELIST_ADDONS`/`REQUIRED_PREFIXES`, rebuilt from what's actually installed on the gold device rather than the old stale `glossary.py` list). `deploy.py` calls `prune_addons()` on the extracted `addons/` folder before pushing — anything not whitelisted (by exact name or a generic prefix like `script.module.`/`service.`/`metadata.`/`resource.`/`inputstream.`/`repository.`) is deleted from the local extracted copy first. Capture itself still doesn't prune addons — only on-device cache/thumbnail junk (`PRE_CAPTURE_PRUNE_PATHS`) before tarring — so a capture stays a faithful full snapshot; filtering happens at deploy time only.
- **Deploy no longer wipes and re-pushes everything.** `AdbClient.sync_tree()` (`_adb.py`, replacing the old `push_tree`) hashes both sides (`find ... -exec md5sum {} +` on-device, `hashlib.md5` locally) and only pushes new/changed files, removing remote files with no local counterpart — same end state as the old full wipe, without re-transferring unchanged files over ADB on every run.
- **Base Kodi APK install is automatic**, not flag-gated, and reused across a `--batch` run: `deploy.py`'s `resolve_base_apk()` downloads `gold/kodi-latest.apk` from SMB once; `cli.py`'s `deploy` command resolves it a single time and passes the same local file into every device's `run_deploy` call (`base_apk_local=`) instead of re-downloading per device. `service.py`'s `deploy_all()` (used by the HA integration) does not yet share this optimization — each concurrently-dispatched job still resolves its own copy; left as a known scope gap since coordinating a shared file's lifetime across concurrent background threads is a materially different problem than the CLI's sequential loop.
- **`BackupRef` (`_artifacts.py`) owns naming** — `device_dir/filename.tar.gz`, where `device_dir` is `sanitize_device_name(device.name)` (or `"gold"` for the shared base image). Latest-backup resolution sorts `.tar.gz` filenames lexically among SMB `scandir` results, which works because names are `.kodi_YYYYMMDD_HHMMSS.tar.gz`.
- **Capture uses `tar cf` + a separate `gzip` pass, not `tar czf`.** Toybox's `tar -z` integration silently produced a truncated gzip stream on a real device (`tar` itself reported success) — split into two steps after verifying `tar cf` alone was clean. `capture.py` also runs `_verify_gzip()` on the pulled archive before uploading, so a bad capture fails loudly instead of silently landing on SMB as if it were good (see `gotcha_toybox_tar_gzip_truncation` memory).
- **Settings overrides are applied at deploy time, not on the gold source.** `_settings_overrides.py`'s `SETTING_OVERRIDES` dict + `remove_thumbnail_path_substitution()` patch specific known-bad values in the extracted `userdata/` before pushing (currently: Arctic Fuse's `startup.enablehubpreloading` off, TMDbHelper's `max_threads` capped at 4, and a network-SMB thumbnail `pathsubstitution` removed so caching stays local). **Never hand-edit these directly on the gold source device** — encode the fix here instead and prove it on a disposable device first; the gold device is the one thing every future capture depends on (see `feedback_gold_device_protection` memory).

## Arctic Fuse 3 Home UI — HomeSwitcher + TMDbHelper Custom Nodes

Arctic Fuse 3 does **not** use `script.skinshortcuts` (that's an older-skin pattern) — its home-tab system is built into the skin itself, called **HomeSwitcher**, and content comes from **TMDbHelper custom nodes**. This is what the skin's own in-Kodi settings UI edits when you add a section like "Genres" or "New TV" — both pieces below can be hand-authored/scripted instead of going through that UI.

### 1. TMDbHelper custom node (the actual content)

A JSON file under `userdata/addon_data/plugin.video.themoviedb.helper/nodes/<name>.json`:

```json
{
  "name": "GENRES HUB",
  "icon": "special://home/addons/plugin.video.themoviedb.helper/resources/icons/white/genres.png",
  "list": [
    {
      "name": "Comedy Series",
      "icon": "special://home/addons/plugin.video.themoviedb.helper/resources/icons/themoviedb/tv.png",
      "path": "plugin://plugin.video.themoviedb.helper/?info=discover&with_id=True&tmdb_type=tv&with_genres=35&sort_by=popularity.desc&vote_count.gte=100&widget=True"
    },
    {
      "name": "Continue Watching",
      "path": "library://video/tvshows/inprogressshows.xml/",
      "widget": "True"
    }
  ]
}
```

Each `list` entry is one row in the hub. `path` is either:
- `plugin://plugin.video.themoviedb.helper/?info=discover&...` — a live TMDb discover query. Common params: `tmdb_type=movie|tv`, `with_genres=<TMDB genre id>` (pipe `%7C` = OR, e.g. `28%7C12`), `with_networks=<id>` (e.g. `213`=Netflix, `49%7C3186`=HBO/Max, `2552`=Apple TV+), `sort_by=popularity.desc` / `first_air_date.desc`, `vote_count.gte=<N>` (quality floor), `first_air_date.lte=T-0&first_air_date.gte=T-90` (relative-date window, e.g. for "new releases" in the last 90 days), `with_original_language=en`, `widget=True`.
- `plugin://plugin.video.themoviedb.helper/?info=dir_custom_node&filename=<other>.json&basedir=special%3A%2F%2Fprofile%2Faddon_data%2Fplugin.video.themoviedb.helper%2Fnodes%2F&widget=true` — links to another node file (nesting hubs).
- `library://video/tvshows/inprogressshows.xml/` — a built-in Kodi library smartlist (no TMDbHelper involved).

Add `"widget": "True"` on a row to mark it widget-eligible (thin horizontal scroller) rather than a full browse page.

### 1b. The three layers (and how they drift)

A hub is defined across **three** separate files, and the captured gold config had them out of sync (e.g. Movies listed 7 rows as a node but only 4 as widgets):

| Layer | Path | What it controls |
|---|---|---|
| HomeSwitcher slot | `skin.arctic.fuse.3/settings.xml` | the top-level tab itself (name, icon, target) |
| Submenu | `script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-<slot>submenu.json` | sub-tabs, each with nested rows |
| Widgets | `…/skinvariables-shortcut-<slot>widgets.json` | the rows rendered on the home screen |
| Node | `plugin.video.themoviedb.helper/nodes/<name>.json` | what shows when you navigate *into* the hub |

`_hub_layout.py` generates the last three from one `HUBS` definition so they can't drift. Schema notes verified against real device files: a submenu parent is `{label, path:"Custom_Submenu", icon, target:"", guid, submenu:[…]}`; a child is `{label, path, icon, target:"videos", guid}`; **every submenu ends with a blank entry** (`label:""`, `submenu:[]`, `widgets:[]`, a guid) — that's the skin's own "add item" affordance, *not* stray data, so generated files reproduce it. `guid`s are `guid-<8 hex>`; `_hub_layout.py` derives them deterministically from the label so regenerating an unchanged hub is byte-identical and `sync_tree` won't re-push it.

**Slot 1104 had no submenu file at all** — that's why it was a flat wall of ten live TMDb queries with zero local content, and why it preceded an OOM kill. Managed slots are `home/1101/1102/1104`; **1103 (Crime), 1107 (Live TV/IPTV) and 1108 are deliberately never touched.**

### 2. HomeSwitcher tab wiring (`skin.arctic.fuse.3/settings.xml`)

Each home tab is a numeric slot (observed: `1101`–`1104`, plus a fixed `Home` slot). Settings keys appear in **both** lowercase and `PascalCase` forms in the same file (skin-version artifact — preserve both if editing by hand, don't assume one is dead):

```
HomeSwitcher.<slot>.Name           = "Genres"
HomeSwitcher.<slot>.Shortcut.Path  = plugin://plugin.video.themoviedb.helper/?info=dir_custom_node&filename=genres_hub.json&basedir=special%3A%2F%2Fprofile%2Faddon_data%2Fplugin.video.themoviedb.helper%2Fnodes%2F&reload=%24INFO%5BWindow%28Home%29.Property%28TMDbHelper.Widgets.Reload%29%5D&widget=true
HomeSwitcher.<slot>.Shortcut.label = "Genres"
HomeSwitcher.<slot>.Shortcut.icon  = image://<url-encoded local icon path>/
HomeSwitcher.<slot>.Spotlight.Path = plugin://plugin.video.themoviedb.helper/?info=trending_day&tmdb_type=tv&reload=$INFO[Window(Home).Property(TMDbHelper.Widgets.Reload)]&widget=true
```

`Shortcut.Path` is the tab's main content (points at a node file via `dir_custom_node`); `Spotlight.Path` is the background/banner widget shown behind the tab (usually a canned `info=` query like `trending_day`/`now_playing`/`popular`, not a custom node). The `reload=$INFO[Window(Home).Property(TMDbHelper.Widgets.Reload)]` suffix is what makes TMDbHelper refresh the widget on skin reload — keep it on any path used as a Shortcut/Spotlight.

**To add a new home section by hand**: write the node JSON under `nodes/`, then add a new `HomeSwitcher.<next-free-slot>.*` block in `settings.xml` pointing `Shortcut.Path` at it. Both files are plain text/JSON — no need to go through Arctic Fuse's or TMDbHelper's own configuration wizard. Verify current slot numbers and exact key casing on the live device first (`adb pull .../skin.arctic.fuse.3/settings.xml`) since duplicate keys can exist from skin-version migrations.

`_kodi.py`'s `collect_kodi_metadata()` checks `skin.arctic.fuse.3` first, then falls back to `.2`/unversioned — fixed 2026-07-30 after it was found always checking the older skin IDs and silently missing the actual target skin (see `reference_kodi_target.md`). Verified against a live device: resolves to e.g. `3.2.15`.

## Argument: $ARGUMENTS

If a build name, device IP, or a specific home-UI section is given, walk through that specific capture/deploy/UI-build scenario. Otherwise explain the general workflow.

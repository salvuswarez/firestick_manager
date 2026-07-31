---
name: fire-tools-cli
description: Reference for every fire-tools subcommand (this repo's CLI, entry point src/fire_tools/cli.py) — flags, defaults, and what each one actually does. Use when running or explaining fire-tools commands.
---

# fire-tools CLI Reference

`fire-tools` is a Click group installed via `pyproject.toml`'s `[project.scripts]` entry (`fire_tools.cli:main`). Always invoke through `uv run fire-tools ...` from the repo root. Every command is a thin wrapper (`cli.py`) over the same job bodies in `src/fire_tools/jobs/` used by `FleetService` (e.g. an HA integration) — see the `kodi-gold-config` skill for the capture/deploy lifecycle and `devices-config` for the `devices.yml` schema these commands read/write.

Backups and the base Kodi APK live only on the SMB share (`SmbConfig.smb_backup_dir`) — there is no local `assets/`/`archive/` tree in the current architecture. Per-job staging (`~/.fire_tools/staging/`) is transient and cleaned up after each run.

## Commands

| Command | Flags | What it does |
|---------|-------|---------------|
| `download` | — | Downloads the latest stable ARMv7 Kodi APK from `mirrors.kodi.tv` and publishes it as `gold/kodi-latest.apk` on the SMB share (`jobs/fetch_base.py`) |
| `maintain [ip]` | `--batch` | Debloat + speed up UI + block telemetry + clean cache on one device (`ip`) or every device in `devices.yml` (`--batch`) |
| `deploy [ip]` | `--batch`, `--backup <device_dir>/<file>.tar.gz` | Downloads a backup from SMB (explicit `--backup`, or the device's latest), extracts it, prunes addons to the whitelist, applies known-good settings overrides, installs the base APK if the device isn't already on that version, syncs `addons`/`userdata`/`media` (hash-diff push via `AdbClient.sync_tree`, not a full wipe), then reapplies the device's stored `display` (resolution_index/overscan) calibration from `devices.yml` if it has one |
| `capture <ip>` | `--name <name>` | Tars the device's live `.kodi` dir, verifies the gzip, uploads it to SMB (no local copy kept), and records the device's current Kodi resolution/overscan calibration into `devices.yml` (`display` field) for `deploy` to reapply later |
| `apply-display <ip>` | `--resolution-index <int>`, `--overscan LEFT TOP RIGHT BOTTOM` | One-off: patches resolution index and/or overscan directly into an already-deployed device's `guisettings.xml` via `sed`. Does **not** touch `devices.yml` — re-run `capture` afterward to persist the new value for future deploys |
| `list-backups` | — | Lists backups found on the SMB share (filename, date, size) |
| `scan` | `--subnet <x.x.x>` (default `192.168.50`) | Parallel ping + ARP + ADB-identify sweep of a `/24`; reconciles results into `resources/devices.yml` by MAC, then serial, then IP |

## Common Invocations

```bash
uv run fire-tools scan --subnet 192.168.50                          # refresh device inventory
uv run fire-tools maintain --batch                                  # debloat the whole fleet
uv run fire-tools capture 192.168.1.50                               # snapshot one device + record its display calibration
uv run fire-tools deploy --batch                                    # full fleet redeploy (base APK auto-installed if stale, per-device display reapplied)
uv run fire-tools apply-display 192.168.1.50 --resolution-index 16 --overscan 0 0 1920 1080
uv run fire-tools list-backups                                      # what's on SMB right now
```

## Error Modes

- `maintain`/`deploy` without an IP and without `--batch` raise `click.UsageError("Provide an IP or use --batch")` — both commands require one or the other.
- `apply-display` with neither `--resolution-index` nor `--overscan` raises `click.UsageError("Provide --resolution-index and/or --overscan")`.
- `deploy` with no matching backup on SMB (no `--backup` given and none found under the device's dir) fails the job with `"No backups found"`.
- `deploy` applying an invalid/malformed stored `display` value from a hand-edited `devices.yml` logs a warning and skips it — the rest of the deploy still completes.
- `download` fails the job with `"No stable APK found"` if the mirror's directory listing has only beta/rc/alpha/nightly builds (or is unreachable).
- `list-backups` prints `"[!] SMB is not configured — set SMB_USER/SMB_PASS in .env"` if `SmbConfig.has_smb` is false, or `"[!] No backups found on SMB share."` if the share has none.
- Any job failure (raised inside a `jobs/*.py` body) surfaces as `click.ClickException(op.result)` — the CLI prints `Error: <message>` and exits non-zero.

## Argument: $ARGUMENTS

If a specific command name is given, explain or run just that command. Otherwise, summarize the full command surface.

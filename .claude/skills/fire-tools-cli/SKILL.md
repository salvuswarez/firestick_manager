---
name: fire-tools-cli
description: Reference for every fire-tools subcommand (this repo's CLI, entry point src/fire_tools/cli.py) — flags, defaults, and what each one actually does. Use when running or explaining fire-tools commands.
---

# fire-tools CLI Reference

`fire-tools` is a Click group installed via `pyproject.toml`'s `[project.scripts]` entry (`fire_tools.cli:main`). Always invoke through `uv run fire-tools ...` from the repo root.

## Commands

| Command | Flags | What it does |
|---------|-------|---------------|
| `download` | — | Downloads the latest stable ARMv7 Kodi APK from the Kodi mirror into `assets/latest_kodi.apk` |
| `maintain [ip]` | `--batch` | Debloat + speed up UI + block telemetry + clean cache on one device (`ip`) or every device in `devices.yml` (`--batch`) |
| `deploy [ip]` | `--batch`, `--update`, `--prep` | Deploy the latest captured build to a device. `--update` installs the local APK first; `--prep` runs `JUNK_PATHS`/addon-whitelist cleanup on the local build before pushing |
| `capture <ip>` | — | Pulls the device's live `.kodi` folder into a new timestamped `assets/.kodi_<YYYYMMDD_HHMMSS>/` snapshot |
| `scan` | `--subnet <x.x.x>` (default `192.168.50`) | Parallel ping + ARP + ADB-identify sweep of a `/24`; rewrites `resources/devices.yml` |

## Common Invocations

```bash
uv run fire-tools scan --subnet 192.168.50        # refresh device inventory
uv run fire-tools maintain --batch                # debloat the whole fleet
uv run fire-tools capture 192.168.1.50             # snapshot one device
uv run fire-tools deploy --batch --update --prep   # full fleet redeploy with fresh APK + pruned config
```

## Error Modes

- `maintain`/`deploy` without an IP and without `--batch` raise `click.UsageError("Provide an IP or use --batch")` — both commands require one or the other.
- `deploy` with no captured build under `assets/.kodi_*` prints `"[!] Error: No captured builds found in assets."` and returns without pushing anything.
- `download` prints `"Could not access mirror directory."` if the Kodi mirror is unreachable, or `"No stable APKs found."` if the directory listing has only beta/rc builds.

## Argument: $ARGUMENTS

If a specific command name is given, explain or run just that command. Otherwise, summarize the full command surface.

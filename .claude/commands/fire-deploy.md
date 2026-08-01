Deploy a built Kodi profile to one or all devices. Argument: `$ARGUMENTS` is a device IP, or `--batch` for the whole fleet (default: ask which if omitted).

1. Confirm scope: single IP or `--batch` (all devices in `resources/devices.yml`).
2. Confirm a build exists on SMB under `builds/`. Deploy only ships builds — if the user wants recent capture changes included, run `/fire-build` first. A `--backup` reference outside `builds/` is rejected.
3. Optionally ask whether to target a specific build via `--backup builds/<filename>.tar.gz` (default: the latest build).
4. Run `uv run fire-tools deploy $ARGUMENTS [--backup ...]`.
5. Report per-device success/failure.

Deploy pushes the build as a single archive and extracts it on-device, replacing `addons`/`userdata`/`media` wholesale. Its only per-device work is the base Kodi APK version check (installed automatically from `gold/kodi-latest.apk` if the device isn't already on that version — there is no `--update`/`--prep` flag) and reapplying that device's `display` calibration and `settings` overrides from `devices.yml`.

Use the `kodi-gold-config` skill for the capture → build → deploy flow, and `devices-config` for per-device `display` and `settings`. This replaces real config on a live device — confirm scope with the user before running, don't default to `--batch` silently.

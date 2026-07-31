Deploy a Kodi backup to one or all devices. Argument: `$ARGUMENTS` is a device IP, or `--batch` for the whole fleet (default: ask which if omitted).

1. Confirm scope: single IP or `--batch` (all devices in `resources/devices.yml`).
2. Optionally ask whether to target a specific backup via `--backup <device_dir>/<filename>.tar.gz` (default: latest backup for that device, resolved from SMB listing).
3. Run `uv run fire-tools deploy $ARGUMENTS [--backup ...]`.
4. Report per-device success/failure. Note: the base Kodi APK is installed automatically if `gold/kodi-latest.apk` exists on the SMB share — there is no `--update`/`--prep` flag anymore (both were removed in the SMB-based rewrite).

Use the `kodi-gold-config` skill for the current capture/deploy flow, and `devices-config` for per-device `display` (resolution_index/overscan) calibration — captured automatically during `capture`, reapplied automatically during `deploy`. This pushes real config to a live device — confirm scope with the user before running, don't default to `--batch` silently.

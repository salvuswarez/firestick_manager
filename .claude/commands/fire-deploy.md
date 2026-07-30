Deploy the latest captured Kodi build to one or all devices. Argument: `$ARGUMENTS` is a device IP, or `--batch` for the whole fleet (default: ask which if omitted).

1. Confirm scope: single IP or `--batch` (all devices in `resources/devices.yml`).
2. Ask whether to include `--update` (push the local `latest_kodi.apk`) and `--prep` (prune `JUNK_PATHS`/non-whitelisted addons before pushing) — don't assume either.
3. Run `uv run fire-tools deploy $ARGUMENTS [--update] [--prep]`.
4. Report per-device success/failure and any "no captured builds found" errors.

Use the `kodi-gold-config` skill for what `--prep` actually prunes, and `devices-config` for how per-device `resolution` gets applied. This pushes real config to a live device — confirm scope with the user before running, don't default to `--batch` silently.

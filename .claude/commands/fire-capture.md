Capture a gold Kodi config snapshot from a device. Argument: `$ARGUMENTS` is the device IP (required — ask if not given).

1. Confirm the target IP is in `resources/devices.yml` (warn if not, but proceed if the user confirms).
2. Run `uv run fire-tools capture $ARGUMENTS`.
3. Report the new `assets/.kodi_<timestamp>/` folder path and its rough size (`du -sh`).
4. Remind the user that `--prep` cleanup does NOT run automatically — suggest `/fire-deploy ... --prep` if they want a pruned copy.

Use the `kodi-gold-config` skill for the full capture/prep/deploy lifecycle.

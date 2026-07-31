Capture a gold Kodi config snapshot from a device. Argument: `$ARGUMENTS` is the device IP (required — ask if not given).

1. Confirm the target IP is in `resources/devices.yml` (warn if not, but proceed if the user confirms).
2. Run `uv run fire-tools capture $ARGUMENTS` (optionally `--name <custom-name>`).
3. Report the SMB path it was uploaded to (`kodi-wan/ha_storage/backups/<device>/.kodi_<timestamp>.tar.gz` or similar — path depends on `SMB_BACKUP_DIR`).
4. There is no local copy and no pruning step — capture tars the on-device `.kodi/` dir, pulls it to a per-job staging dir, uploads to SMB, then discards the local staging copy. If disk/addon cleanup is needed, that happens on-device before capture via `PRE_CAPTURE_PRUNE_PATHS` (cache/thumbnail junk only, not addons).
5. Capture also reads the device's live Kodi resolution/overscan and records it into `resources/devices.yml` (`display` field) — only if that device is already known there. `deploy` reapplies it automatically afterward. If the user just recalibrated a device live (or via `apply-display`), re-running `capture` is how that gets persisted for future deploys.

Use the `kodi-gold-config` skill for the full capture/deploy lifecycle and the Arctic Fuse home-UI (HomeSwitcher/TMDbHelper node) reference.

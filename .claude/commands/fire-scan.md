Scan the local network for Fire TV Sticks and refresh `resources/devices.yml`. Argument: `$ARGUMENTS` is the subnet prefix (default `192.168.50`).

1. Run `uv run fire-tools scan --subnet ${ARGUMENTS:-192.168.50}`.
2. Show the resulting `resources/devices.yml` diff (new/removed/changed devices).
3. Flag if any previously-known device (by MAC) is now missing.

Use the `devices-config` skill for the file schema. Never overwrite a device's stored `display` (resolution_index/overscan) field — scan only writes `ip`/`mac`/`name`/`model`/`serial`/`android_version` (via MAC/serial/IP reconciliation) and never touches `display`; that's written by `capture` instead.

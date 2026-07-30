Scan the local network for Fire TV Sticks and refresh `resources/devices.yml`. Argument: `$ARGUMENTS` is the subnet prefix (default `192.168.50`).

1. Run `uv run fire-tools scan --subnet ${ARGUMENTS:-192.168.50}`.
2. Show the resulting `resources/devices.yml` diff (new/removed/changed devices).
3. Flag if any previously-known device (by MAC) is now missing.

Use the `devices-config` skill for the file schema. Never overwrite hand-added `resolution` fields — the scan only writes `ip`/`mac`/`name`; merge rather than blindly replacing if the file already has resolution overrides.

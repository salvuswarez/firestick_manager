Scan the local network for Fire TV Sticks and refresh `resources/devices.yml`. Argument: `$ARGUMENTS` is the subnet prefix (default `192.168.50`).

1. Run `uv run fire-tools scan --subnet ${ARGUMENTS:-192.168.50}`.
2. Show the resulting `resources/devices.yml` diff (new/removed/changed devices).
3. Flag if any previously-known device (by MAC) is now missing.

Use the `devices-config` skill for the file schema. Scan is the fleet's metadata refresh: it writes `ip`/`mac`/`name`/`model`/`serial`/`android_version` **and `display`** (resolution_index/overscan, read from each device's live `guisettings.xml`), reconciling by MAC, then serial, then IP. It never touches `settings`, which is hand-maintained. A field is only overwritten when the probe actually returned a value, so a sleeping device keeps what was already stored.

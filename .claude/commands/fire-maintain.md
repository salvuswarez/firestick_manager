Run debloat, animation speedup, telemetry blocking, and cache cleanup on one or all devices. Argument: `$ARGUMENTS` is a device IP, or `--batch` for the whole fleet.

1. Confirm scope: single IP or `--batch`.
2. Run `uv run fire-tools maintain $ARGUMENTS`.
3. Report which packages were disabled per device and note any that were already disabled (Fire OS 5+ may reject `pm disable-user` on some system packages — see the `adb-device-ops` skill).

Use the `fleet-device-specialist` agent's context on `BLOAT_PACKAGES` if the user wants to add/remove a package from the debloat list.

Build a deployable Kodi profile from a capture and publish it to SMB. Argument: `$ARGUMENTS` is an optional source capture reference (`<device_dir>/<filename>.tar.gz`); omit it to use the latest capture under `gold/`.

1. Confirm the source: explicit `--source`, or the latest gold capture (state which one will be used).
2. Run `uv run fire-tools build [--source $ARGUMENTS]`.
3. Report the published build path and the transforms that reported changes.

Build is where **all** profile shaping happens, once, for the whole fleet: addon whitelist pruning (`_addon_policy.py`), settings overrides (`_settings_overrides.py`), home-screen hub layout (`_hub_layout.py`), and view-type fixes (`_view_types.py`). The result is repacked flat (`addons`/`userdata`/`media` at the tar root) into `builds/` on SMB, and `deploy` does nothing but transfer it.

If a change should apply to every device, it belongs in one of those modules — rebuild, then deploy. If it must differ per device, it belongs in that device's `settings` block in `devices.yml` instead (see the `devices-config` skill).

Use the `kodi-gold-config` skill for the full capture → build → deploy lifecycle. This only writes to SMB, never to a device — it's safe to re-run.

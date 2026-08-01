"""Per-device Kodi setting overrides, applied on-device after a deploy.

A build is one artifact shared by the whole fleet, so anything that differs
per stick can't live in it. `Device.settings` in `devices.yml` carries those
differences and they're patched onto the device after extraction, the same
way display calibration is.

Shape mirrors `_settings_overrides.SETTING_OVERRIDES` — `{userdata-relative
file: {setting_id: value}}`:

    settings:
      guisettings.xml:
        audiooutput.channels: "1"
      addon_data/pvr.iptvsimple/settings.xml:
        m3uPath: "http://192.168.1.50/playlist.m3u"

Values come from a hand-edited file and are interpolated into a `sed` command,
so both the path and every id/value are validated before they reach a shell.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING, Any

from .const import REMOTE_KODI_PATH

if TYPE_CHECKING:
    from ._adb import AdbClient

_SAFE_REL_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
_SAFE_SETTING_ID = re.compile(r"^[A-Za-z0-9._#-]+$")
# `<` and `&` would corrupt the XML; `|` is the sed delimiter used below.
_UNSAFE_VALUE_CHARS = re.compile(r"[<>&|\r\n]")


def validate_device_settings(settings: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Validate a device's `settings` block from the device store.

    **PARAMETERS:**
        `settings` (dict[str, Any]): Raw ``{rel_path: {setting_id: value}}`` as loaded from `devices.yml`.  <br>

    **RETURNS:**
        `dict[str, dict[str, str]]`: The same mapping with every value coerced to `str`.  <br>

    **RAISES:**
        `ValueError`: If a path escapes ``userdata/``, or an id/value contains characters that aren't safe in a `sed` expression.  <br>
    """
    validated: dict[str, dict[str, str]] = {}
    for rel_path, overrides in settings.items():
        if not _SAFE_REL_PATH.match(str(rel_path)) or ".." in str(rel_path):
            raise ValueError(f"Unsafe settings path: {rel_path!r}")
        if not isinstance(overrides, dict):
            raise ValueError(f"settings[{rel_path!r}] must be a mapping of setting id to value")
        entries: dict[str, str] = {}
        for setting_id, value in overrides.items():
            if not _SAFE_SETTING_ID.match(str(setting_id)):
                raise ValueError(f"Unsafe setting id: {setting_id!r}")
            text = str(value)
            if _UNSAFE_VALUE_CHARS.search(text):
                raise ValueError(f"Unsafe value for {setting_id!r}: {text!r}")
            entries[str(setting_id)] = text
        if entries:
            validated[str(rel_path)] = entries
    return validated


def apply_device_settings(adb: AdbClient, settings: dict[str, dict[str, str]]) -> list[str]:
    """Patch validated per-device settings into the deployed profile.

    Patches in place with `sed` rather than pushing whole files, so a device's
    overrides don't require rebuilding or re-pushing the shared archive.

    **PARAMETERS:**
        `adb` (AdbClient): An already-connected client for the target device.  <br>
        `settings` (dict[str, dict[str, str]]): Output of `validate_device_settings`.  <br>

    **RETURNS:**
        `list[str]`: Human-readable description of each override applied.  <br>
    """
    applied: list[str] = []
    for rel_path, overrides in settings.items():
        remote = f"{REMOTE_KODI_PATH}/userdata/{rel_path}"
        if not adb.shell_ok(f"test -f {shlex.quote(remote)} && echo ok"):
            applied.append(f"{rel_path}: skipped (not present on device)")
            continue
        for setting_id, value in overrides.items():
            expr = f's|<setting id="{setting_id}">.*</setting>|' f'<setting id="{setting_id}">{value}</setting>|'
            adb.shell(f"sed -i {shlex.quote(expr)} {shlex.quote(remote)}")
            applied.append(f"{rel_path}: {setting_id} = {value}")
    return applied

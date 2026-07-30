"""Display job: patch per-device resolution/overscan into guisettings.xml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .._adb import AdbClient, AdbKeyStore
from ..const import REMOTE_KODI_PATH
from ..operations import OperationHandle

_GUI_SETTINGS_PATH = f"{REMOTE_KODI_PATH}/userdata/guisettings.xml"
_OVERSCAN_FIELDS = ("left", "top", "right", "bottom")


def run_apply_display(
    handle: OperationHandle, ws: Path, *, ip: str, display_settings: dict[str, Any], adb_keys: AdbKeyStore
) -> str:
    """Patch Kodi's resolution index and/or overscan calibration on a device.

    Requires Kodi to already be deployed (patches the existing
    `guisettings.xml` in place via `sed`, matching Arctic Fuse 3's storage
    format) rather than pushing a whole file, so a concurrent Kodi session
    should be closed first for the change to take effect cleanly.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory (unused by this job).
        ip (str): Target device IP.
        display_settings (dict[str, Any]): `{"resolution_index": int, "overscan":
            {"left": int, "top": int, "right": int, "bottom": int}}`, both optional.
        adb_keys (AdbKeyStore): Shared ADB signer cache.

    RETURNS:
        str: Human-readable result summary.

    RAISES:
        ValueError: If `display_settings` has no recognized fields, or a
            field is present but not an integer.
    """
    resolution_index = display_settings.get("resolution_index")
    overscan = display_settings.get("overscan")
    if resolution_index is None and not overscan:
        raise ValueError("display_settings must include resolution_index and/or overscan")
    if resolution_index is not None and not isinstance(resolution_index, int):
        raise ValueError(f"resolution_index must be an int, got {resolution_index!r}")
    if overscan:
        for field_name in _OVERSCAN_FIELDS:
            value = overscan.get(field_name, 0)
            if not isinstance(value, int):
                raise ValueError(f"overscan.{field_name} must be an int, got {value!r}")

    handle.check_cancelled()
    with AdbClient(ip, adb_keys) as adb:
        if resolution_index is not None:
            handle.log(f"Setting resolution index to {resolution_index}...")
            adb.shell(
                "sed -i 's|<setting id=\"videoscreen.resolution\">.*</setting>|"
                f'<setting id="videoscreen.resolution">{resolution_index}</setting>|\' {_GUI_SETTINGS_PATH}'
            )

        if overscan:
            left = overscan.get("left", 0)
            top = overscan.get("top", 0)
            right = overscan.get("right", 1920)
            bottom = overscan.get("bottom", 1080)
            handle.log(f"Setting overscan: L={left} T={top} R={right} B={bottom}...")
            # Patches only the first <resolutions> block (the active one),
            # matching Kodi's per-resolution overscan storage.
            adb.shell(f'sed -i "0,/<left>.*<\\/left>/s|<left>.*</left>|<left>{left}</left>|" {_GUI_SETTINGS_PATH}')
            adb.shell(f'sed -i "0,/<top>.*<\\/top>/s|<top>.*</top>|<top>{top}</top>|" {_GUI_SETTINGS_PATH}')
            adb.shell(f'sed -i "0,/<right>.*<\\/right>/s|<right>.*</right>|<right>{right}</right>|" {_GUI_SETTINGS_PATH}')
            adb.shell(f'sed -i "0,/<bottom>.*<\\/bottom>/s|<bottom>.*</bottom>|<bottom>{bottom}</bottom>|" {_GUI_SETTINGS_PATH}')

    handle.log(f"Display settings applied to {ip}")
    return f"Display settings applied to {ip}"

"""Display job: patch per-device resolution/overscan into guisettings.xml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .._adb import AdbClient, AdbKeyStore
from ..const import KODI_OVERSCAN_FIELDS, REMOTE_GUISETTINGS_PATH
from ..operations import OperationHandle


def validate_display_settings(display_settings: dict[str, Any]) -> None:
    """Check a `display_settings` dict has at least one recognized, well-typed field.

    Split out from `run_apply_display` so `jobs.deploy` can validate a
    device's stored calibration (which may have been hand-edited in
    `devices.yml`) before patching it back in, without duplicating the rules.

    PARAMETERS:
        display_settings (dict[str, Any]): `{"resolution_index": int, "overscan":
            {"left": int, "top": int, "right": int, "bottom": int}}`, both optional.

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
        for field_name in KODI_OVERSCAN_FIELDS:
            value = overscan.get(field_name, 0)
            if not isinstance(value, int):
                raise ValueError(f"overscan.{field_name} must be an int, got {value!r}")


def patch_display_settings(adb: AdbClient, display_settings: dict[str, Any], handle: OperationHandle) -> None:
    """Patch already-validated resolution/overscan calibration into `guisettings.xml`.

    Requires Kodi to already be deployed (patches the existing
    `guisettings.xml` in place via `sed`, matching Arctic Fuse 3's storage
    format) rather than pushing a whole file, so a concurrent Kodi session
    should be closed first for the change to take effect cleanly.

    PARAMETERS:
        adb (AdbClient): An already-connected ADB client for the device.
        display_settings (dict[str, Any]): Validated via `validate_display_settings`.
        handle (OperationHandle): Handle to log through.
    """
    resolution_index = display_settings.get("resolution_index")
    overscan = display_settings.get("overscan")

    if resolution_index is not None:
        handle.log(f"Setting resolution index to {resolution_index}...")
        adb.shell(
            "sed -i 's|<setting id=\"videoscreen.resolution\">.*</setting>|"
            f'<setting id="videoscreen.resolution">{resolution_index}</setting>|\' {REMOTE_GUISETTINGS_PATH}'
        )

    if overscan:
        left = overscan.get("left", 0)
        top = overscan.get("top", 0)
        right = overscan.get("right", 1920)
        bottom = overscan.get("bottom", 1080)
        handle.log(f"Setting overscan: L={left} T={top} R={right} B={bottom}...")
        # Patches only the first <resolutions> block (the active one),
        # matching Kodi's per-resolution overscan storage.
        adb.shell(f'sed -i "0,/<left>.*<\\/left>/s|<left>.*</left>|<left>{left}</left>|" {REMOTE_GUISETTINGS_PATH}')
        adb.shell(f'sed -i "0,/<top>.*<\\/top>/s|<top>.*</top>|<top>{top}</top>|" {REMOTE_GUISETTINGS_PATH}')
        adb.shell(f'sed -i "0,/<right>.*<\\/right>/s|<right>.*</right>|<right>{right}</right>|" {REMOTE_GUISETTINGS_PATH}')
        adb.shell(f'sed -i "0,/<bottom>.*<\\/bottom>/s|<bottom>.*</bottom>|<bottom>{bottom}</bottom>|" {REMOTE_GUISETTINGS_PATH}')


def run_apply_display(
    handle: OperationHandle, ws: Path, *, ip: str, display_settings: dict[str, Any], adb_keys: AdbKeyStore
) -> str:
    """Patch Kodi's resolution index and/or overscan calibration on a device.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory (unused by this job).
        ip (str): Target device IP.
        display_settings (dict[str, Any]): See `validate_display_settings`.
        adb_keys (AdbKeyStore): Shared ADB signer cache.

    RETURNS:
        str: Human-readable result summary.

    RAISES:
        ValueError: If `display_settings` has no recognized fields, or a
            field is present but not an integer.
    """
    validate_display_settings(display_settings)

    handle.check_cancelled()
    with AdbClient(ip, adb_keys) as adb:
        patch_display_settings(adb, display_settings, handle)

    handle.log(f"Display settings applied to {ip}")
    return f"Display settings applied to {ip}"

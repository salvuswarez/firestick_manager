"""Maintenance job: disable bloatware, trim caches, disable telemetry."""
from __future__ import annotations

import shlex
from pathlib import Path

from .._adb import AdbClient, AdbKeyStore
from ..const import BLOAT_PACKAGES, MAINTENANCE_PRUNE_PATHS, REMOTE_KODI_PATH
from ..operations import OperationHandle


def run_maintain(handle: OperationHandle, ws: Path, *, ip: str, adb_keys: AdbKeyStore) -> str:
    """Disable Amazon bloatware, trim caches, and disable telemetry on a device.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory (unused by this job).
        ip (str): Target device IP.
        adb_keys (AdbKeyStore): Shared ADB signer cache.

    RETURNS:
        str: Human-readable result summary.
    """
    handle.log(f"Connecting to {ip}...")
    with AdbClient(ip, adb_keys) as adb:
        handle.log(f"Disabling {len(BLOAT_PACKAGES)} bloat packages...")
        for pkg in BLOAT_PACKAGES:
            handle.check_cancelled()
            adb.shell_ok(f"pm disable-user --user 0 {pkg}")

        handle.log("Trimming system caches...")
        adb.shell_ok("pm trim-caches 16G")
        adb.shell_ok("pm clear com.amazon.bueller.photos")

        handle.log("Optimizing system performance...")
        adb.shell_ok("settings put global window_animation_scale 0.0")
        adb.shell_ok("settings put global transition_animation_scale 0.0")
        adb.shell_ok("settings put global animator_duration_scale 0.0")
        adb.shell_ok("am trim-memory --all")

        handle.log("Disabling telemetry...")
        adb.shell_ok("settings put secure limit_ad_tracking 1")
        adb.shell_ok("settings put global marketing_allowed 0")
        adb.shell_ok("settings put global data_monitoring_enabled 0")

        handle.check_cancelled()
        handle.log("Cleaning Kodi caches...")
        for rel_path in MAINTENANCE_PRUNE_PATHS:
            adb.shell_ok(f"rm -rf {shlex.quote(f'{REMOTE_KODI_PATH}/{rel_path}')}")

    handle.log("Maintenance complete")
    return f"Maintained {ip}"

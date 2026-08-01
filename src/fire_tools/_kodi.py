"""Kodi/device-health probes shared by the capture job and the check_device command."""

from __future__ import annotations

import re
import socket
from typing import Any

from ._adb import AdbClient
from .const import ADB_PORT, KODI_OVERSCAN_FIELDS, REMOTE_GUISETTINGS_PATH, REMOTE_KODI_PATH


def check_device_online(ip: str, timeout: float = 3.0) -> bool:
    """Check whether a device is accepting ADB connections.

    PARAMETERS:
        ip (str): Device IPv4 address.
        timeout (float): Socket connect timeout in seconds.

    RETURNS:
        bool: True if a TCP connection to the ADB port succeeded.
    """
    try:
        sock = socket.create_connection((ip, ADB_PORT), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def collect_kodi_metadata(adb: AdbClient) -> dict[str, str]:
    """Collect Kodi/Arctic Fuse/Android version info from a connected device.

    PARAMETERS:
        adb (AdbClient): An already-connected ADB client for the device.

    RETURNS:
        dict[str, str]: Any of `kodi_version`, `android_version`,
        `arctic_fuse` that could be determined; missing keys mean unknown.
    """
    meta: dict[str, str] = {}
    dumpsys = adb.shell_ok("dumpsys package org.xbmc.kodi")
    if dumpsys:
        for line in dumpsys.split("\n"):
            line = line.strip()
            if "versionName=" in line:
                meta["kodi_version"] = line.split("=")[-1].strip()
                break
    build = adb.shell_ok("getprop ro.build.version.release")
    if build:
        meta["android_version"] = build.strip()
    for skin in ("skin.arctic.fuse.3", "skin.arctic.fuse.2", "skin.arctic.fuse"):
        addon_xml = adb.shell_ok(f"cat {REMOTE_KODI_PATH}/addons/{skin}/addon.xml")
        if not addon_xml:
            continue
        for line in addon_xml.split("\n"):
            line = line.strip()
            if line.startswith("<addon") and "version=" in line:
                match = re.search(r'version="([^"]+)"', line)
                if match and match.group(1):
                    meta["arctic_fuse"] = match.group(1)
                    return meta
    return meta


def parse_display_settings(xml: str) -> dict[str, Any]:
    """Extract resolution index and overscan calibration from `guisettings.xml`.

    Pure parsing, split from the ADB read so both callers can share it: the
    scan job reaches devices through Scanner's simple `(ip, cmd) -> str`
    runner, while other callers hold a full `AdbClient`.

    Kodi only writes a setting to `guisettings.xml` when it differs from the
    default, so a device that's never been manually calibrated legitimately
    has neither value present — that's an empty dict, not an error, matching
    the `display_settings` shape `jobs.display` reads/writes.

    **PARAMETERS:**
        `xml` (str): Contents of `guisettings.xml`, or `""` if unreadable.  <br>

    **RETURNS:**
        `dict[str, Any]`: ``{"resolution_index": int, "overscan": {...}}``, with either key omitted when not present in the file.  <br>
    """
    if not xml:
        return {}

    settings: dict[str, Any] = {}
    match = re.search(r'<setting id="videoscreen\.resolution">(-?\d+)</setting>', xml)
    if match:
        settings["resolution_index"] = int(match.group(1))

    # First occurrence only, matching `patch_display_settings`'s assumption
    # that the first <resolutions> entry is the active one.
    overscan: dict[str, int] = {}
    for field_name in KODI_OVERSCAN_FIELDS:
        field_match = re.search(rf"<{field_name}>(-?\d+)</{field_name}>", xml)
        if field_match:
            overscan[field_name] = int(field_match.group(1))
    if overscan:
        settings["overscan"] = overscan

    return settings


def collect_kodi_display_settings(adb: AdbClient) -> dict[str, Any]:
    """Read a connected device's Kodi display calibration.

    **PARAMETERS:**
        `adb` (AdbClient): An already-connected ADB client for the device.  <br>

    **RETURNS:**
        `dict[str, Any]`: Same shape as `parse_display_settings`.  <br>
    """
    return parse_display_settings(adb.shell_ok(f"cat {REMOTE_GUISETTINGS_PATH}"))

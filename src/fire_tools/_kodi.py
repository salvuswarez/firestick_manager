"""Kodi/device-health probes shared by the capture job and the check_device command."""
from __future__ import annotations

import re
import socket

from ._adb import AdbClient
from .const import ADB_PORT, REMOTE_KODI_PATH


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

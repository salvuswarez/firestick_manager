"""Fetch-base job: download the latest stable Kodi Android APK to the gold share."""
from __future__ import annotations

import re
import urllib.request
from datetime import datetime
from pathlib import Path

from .._artifacts import GOLD_DEVICE_DIR
from .._smb import SmbClient
from ..models import BackupMeta, SmbConfig
from ..operations import OperationHandle

_MIRROR_URL = "https://mirrors.kodi.tv/releases/android/arm/"
_APK_PATTERN = re.compile(r'href="(kodi-[\d.]+-[^"]+-armeabi-v7a\.apk)"')
_VERSION_PATTERN = re.compile(r"kodi-([\d.]+)-")
_UNSTABLE_MARKERS = ("beta", "rc", "alpha", "nightly")
_DOWNLOAD_TIMEOUT_S = 60.0
_CHUNK_SIZE = 65536


def run_fetch_base(handle: OperationHandle, ws: Path, *, smb: SmbClient, config: SmbConfig) -> str:
    """Download the latest stable Kodi APK and publish it as the shared base image.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory.
        smb (SmbClient): Configured SMB client.
        config (SmbConfig): Resolved SMB backup directory.

    RETURNS:
        str: SMB-relative path of the uploaded APK.

    RAISES:
        RuntimeError: If no stable ARM APK is found on the mirror.
    """
    handle.log("Fetching Kodi APK index from mirrors...")
    apk_names = _list_stable_apks()
    if not apk_names:
        raise RuntimeError("No stable APK found")

    apk_names.sort(key=_version_key, reverse=True)
    latest_name = apk_names[0]
    version_match = _VERSION_PATTERN.search(latest_name)
    kodi_version = version_match.group(1) if version_match else "unknown"
    apk_url = f"{_MIRROR_URL}{latest_name}"

    handle.check_cancelled()
    handle.log(f"Downloading Kodi {kodi_version} APK...")
    apk_path = ws / f"kodi-{kodi_version}.apk"
    _download(apk_url, apk_path)

    handle.check_cancelled()
    smb_remote = f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/kodi-latest.apk"
    handle.log(f"Uploading APK to SMB: {smb_remote}")
    smb.makedirs(f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}")
    file_size = smb.upload_file(str(apk_path), smb_remote)

    meta = BackupMeta(device_name="base", captured_at=datetime.now().isoformat(), kodi_version=kodi_version, size=file_size)
    smb.write_text(f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/kodi-latest.meta.json", meta.model_dump_json(indent=2))

    handle.log(f"Kodi {kodi_version} APK saved to gold/")
    return smb_remote


def _list_stable_apks() -> list[str]:
    req = urllib.request.Request(_MIRROR_URL, headers={"User-Agent": "HomeAssistant/Firetools"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    names = []
    for match in _APK_PATTERN.finditer(html):
        name = match.group(1)
        if any(marker in name.lower() for marker in _UNSTABLE_MARKERS):
            continue
        names.append(name)
    return names


def _version_key(name: str) -> tuple[int, ...]:
    match = _VERSION_PATTERN.search(name)
    if not match:
        return (0, 0, 0)
    parts = [int(p) for p in match.group(1).split(".") if p.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant/Firetools"})
    with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT_S) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(_CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)

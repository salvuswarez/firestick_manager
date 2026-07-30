"""Deploy job: push a backup (or the latest one) to a device."""
from __future__ import annotations

import tarfile
from pathlib import Path

from .._adb import AdbClient, AdbKeyStore
from .._artifacts import GOLD_DEVICE_DIR, BackupRef, sanitize_device_name
from .._kodi import check_device_online
from .._smb import SmbClient
from ..const import REMOTE_KODI_PATH
from ..device_store import DeviceStore
from ..models import SmbConfig
from ..operations import OperationHandle

_BASE_APK_NAME = "kodi-latest.apk"
_DEVICE_APK_PATH = "/sdcard/kodi-latest.apk"


def run_deploy(
    handle: OperationHandle,
    ws: Path,
    *,
    ip: str,
    backup_name: str | None,
    devices: DeviceStore,
    adb_keys: AdbKeyStore,
    smb: SmbClient,
    config: SmbConfig,
) -> str:
    """Deploy a backup archive (or the latest one for this device) to a device.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory.
        ip (str): Target device IP.
        backup_name (str | None): Validated `device_dir/filename` reference,
            or None to deploy the device's most recent backup.
        devices (DeviceStore): Used to resolve the device's display name.
        adb_keys (AdbKeyStore): Shared ADB signer cache.
        smb (SmbClient): Configured SMB client.
        config (SmbConfig): Resolved SMB backup directory.

    RETURNS:
        str: Human-readable result summary.

    RAISES:
        RuntimeError: If the device is offline or no backup can be found.
    """
    handle.log(f"Prepping {ip}...")
    handle.log("Checking device connectivity...")
    if not check_device_online(ip):
        raise RuntimeError(f"Device {ip} offline")

    dev = devices.get_by_ip(ip)
    device_name = dev.name if dev else ip
    safe_name = sanitize_device_name(device_name)

    with AdbClient(ip, adb_keys) as adb:
        _install_base_apk_if_present(handle, ws, smb, config, adb)

        handle.check_cancelled()
        ref = _resolve_backup_ref(handle, backup_name, safe_name, smb, config)

        handle.log(f"Downloading {ref.wire()} from SMB...")
        local_tar = ref.local_path(ws)
        smb.download_file(ref.smb_remote(config.smb_backup_dir), str(local_tar))

        handle.log("Extracting...")
        with tarfile.open(local_tar, "r:gz") as tar:
            tar.extractall(ws, filter="data")
        extracted_path = ws / ref.archive_root

        handle.check_cancelled()
        handle.log(f"Deploying config to {ip}...")
        adb.shell_ok("am force-stop org.xbmc.kodi")
        adb.shell(f"rm -rf {REMOTE_KODI_PATH}")
        adb.shell(f"mkdir -p {REMOTE_KODI_PATH}")

        for folder in ("addons", "userdata", "media"):
            local = extracted_path / folder
            if local.exists():
                handle.log(f"Pushing {folder}...")
                adb.push_tree(str(local), f"{REMOTE_KODI_PATH}/{folder}")

    handle.log(f"Deployment finished for {ip}")
    return f"Deployed to {ip}"


def _install_base_apk_if_present(
    handle: OperationHandle, ws: Path, smb: SmbClient, config: SmbConfig, adb: AdbClient
) -> None:
    base_smb_remote = f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/{_BASE_APK_NAME}"
    local_apk = ws / _BASE_APK_NAME
    try:
        smb.download_file(base_smb_remote, str(local_apk))
    except OSError:
        handle.log("No base APK found on SMB, skipping Kodi install")
        return
    handle.log("Base Kodi APK found, installing...")
    adb.push_file(str(local_apk), _DEVICE_APK_PATH)
    adb.shell(f"pm install -r {_DEVICE_APK_PATH}")
    adb.shell_ok(f"rm -f {_DEVICE_APK_PATH}")
    handle.log("Base Kodi installed")


def _resolve_backup_ref(
    handle: OperationHandle, backup_name: str | None, safe_name: str, smb: SmbClient, config: SmbConfig
) -> BackupRef:
    if backup_name:
        return BackupRef.parse(backup_name)

    handle.log("Finding latest backup...")
    candidates: list[str] = []
    try:
        for entry in smb.scandir(f"{config.smb_backup_dir}/{safe_name}"):
            if entry.name.endswith(".tar.gz") and ".kodi_" in entry.name:
                candidates.append(entry.name)
    except Exception:
        pass
    if not candidates:
        raise RuntimeError("No backups found")
    return BackupRef(device_dir=safe_name, filename=sorted(candidates)[-1])

"""Capture job: archive a device's Kodi profile and upload it to SMB."""
from __future__ import annotations

import os
import shlex
from datetime import datetime
from pathlib import Path

from .._adb import AdbClient, AdbKeyStore
from .._artifacts import GOLD_DEVICE_DIR, BackupRef, sanitize_device_name, validate_backup_name
from .._kodi import collect_kodi_metadata
from .._smb import SmbClient
from ..const import PRE_CAPTURE_PRUNE_PATHS, REMOTE_KODI_PATH
from ..device_store import DeviceStore
from ..models import BackupMeta, SmbConfig
from ..operations import OperationHandle


def run_capture(
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
    """Archive a device's `.kodi` directory and upload it to SMB.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory.
        ip (str): Target device IP.
        backup_name (str | None): Validated single-segment name, or None to
            auto-generate `.kodi_<timestamp>`.
        devices (DeviceStore): Used to resolve the device's display name.
        adb_keys (AdbKeyStore): Shared ADB signer cache.
        smb (SmbClient): Configured SMB client.
        config (SmbConfig): Resolved SMB backup directory.

    RETURNS:
        str: The SMB-relative path of the uploaded archive.
    """
    handle.log(f"Connecting to {ip}...")
    dev = devices.get_by_ip(ip)
    device_name = dev.name if dev else ip
    device_mac = (dev.mac if dev and dev.mac else "") or ip.replace(".", "_")
    safe_name = sanitize_device_name(device_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = validate_backup_name(backup_name) if backup_name else f".kodi_{timestamp}"
    is_gold = name.startswith("gold-") or name.startswith("base-")
    device_dir = GOLD_DEVICE_DIR if is_gold else safe_name
    ref = BackupRef.for_capture(device_dir, name)
    device_tar = f"/sdcard/{ref.filename}"

    handle.check_cancelled()
    handle.log("Collecting metadata...")
    with AdbClient(ip, adb_keys) as adb:
        meta = collect_kodi_metadata(adb)
        backup_meta = BackupMeta(
            device_name="gold" if is_gold else device_name,
            device_mac=device_mac,
            device_ip=ip,
            captured_at=datetime.now().isoformat(),
            kodi_version=meta.get("kodi_version", ""),
            arctic_fuse=meta.get("arctic_fuse", ""),
            android_version=meta.get("android_version", ""),
        )

        handle.check_cancelled()
        handle.log("Cleaning cache junk on-device...")
        for rel_path in PRE_CAPTURE_PRUNE_PATHS:
            adb.shell_ok(f"rm -rf {shlex.quote(f'{REMOTE_KODI_PATH}/{rel_path}')}")

        handle.check_cancelled()
        handle.log("Creating tar.gz on device...")
        adb.shell(
            f"tar czf {shlex.quote(device_tar)} "
            f"-C {shlex.quote(os.path.dirname(REMOTE_KODI_PATH))} {ref.archive_root}"
        )

        handle.log("Pulling compressed archive...")
        local_tar = ref.local_path(ws)
        adb.pull(device_tar, str(local_tar))
        adb.shell_ok(f"rm -f {shlex.quote(device_tar)}")

    handle.check_cancelled()
    smb_remote = ref.smb_remote(config.smb_backup_dir)
    handle.log(f"Uploading to SMB: {smb_remote}")
    smb.makedirs(f"{config.smb_backup_dir}/{device_dir}")
    file_size = smb.upload_file(str(local_tar), smb_remote)
    backup_meta.size = file_size
    smb.write_text(ref.smb_meta_remote(config.smb_backup_dir), backup_meta.model_dump_json(indent=2))

    handle.log(f"Captured and saved: {smb_remote}")
    return smb_remote

"""Deploy job: push a backup (or the latest one) to a device."""
from __future__ import annotations

import json
import logging
import tarfile
from pathlib import Path

from .._adb import AdbClient, AdbKeyStore
from .._addon_policy import prune_addons
from .._artifacts import GOLD_DEVICE_DIR, BackupRef, sanitize_device_name
from .._hub_layout import apply_hub_layout
from .._kodi import check_device_online, collect_kodi_metadata
from .._settings_overrides import apply_setting_overrides, remove_thumbnail_path_substitution
from .._smb import SmbClient
from ..const import REMOTE_KODI_PATH
from ..device_store import DeviceStore
from ..models import SmbConfig
from ..operations import OperationHandle

LOGGER = logging.getLogger(__name__)

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
    base_apk_local: Path | None = None,
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
        base_apk_local (Path | None): Pre-downloaded base APK to install.
            Pass this when deploying to multiple devices in one run (see
            `resolve_base_apk`) so the same file isn't re-fetched from SMB
            once per device. If None, this job resolves it itself.

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
        _install_base_apk(handle, ws, smb, config, adb, base_apk_local)

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
        handle.log("Pruning addons to the gold whitelist...")
        removed = prune_addons(extracted_path / "addons")
        if removed:
            handle.log(f"Removed {len(removed)} non-whitelisted addon(s): {', '.join(removed)}")

        handle.check_cancelled()
        handle.log("Applying known-good settings overrides...")
        for change in apply_setting_overrides(extracted_path / "userdata"):
            handle.log(f"  {change}")
        if remove_thumbnail_path_substitution(extracted_path / "userdata"):
            handle.log("  advancedsettings.xml: removed network thumbnail path substitution")

        handle.check_cancelled()
        handle.log("Regenerating home-screen hub layout...")
        for change in apply_hub_layout(extracted_path / "userdata"):
            handle.log(f"  {change}")

        handle.check_cancelled()
        handle.log(f"Deploying config to {ip}...")
        adb.shell_ok("am force-stop org.xbmc.kodi")
        adb.shell(f"mkdir -p {REMOTE_KODI_PATH}")

        for folder in ("addons", "userdata", "media"):
            local = extracted_path / folder
            if local.exists():
                handle.log(f"Syncing {folder}...")
                pushed, removed_count = adb.sync_tree(str(local), f"{REMOTE_KODI_PATH}/{folder}")
                handle.log(f"  {folder}: {pushed} changed, {removed_count} removed, rest unchanged")

    handle.log(f"Deployment finished for {ip}")
    return f"Deployed to {ip}"


def resolve_base_apk(ws: Path, smb: SmbClient, config: SmbConfig) -> Path | None:
    """Download the shared base Kodi APK from SMB, if one has been published.

    Split out from `_install_base_apk` so a batch deploy (`cli.py`'s
    `--batch`, or any future fleet-wide caller) can resolve it once and pass
    the same local file into every device's `run_deploy` call, instead of
    downloading the same ~30-80MB file once per device.

    PARAMETERS:
        ws (Path): Staging directory to download into.
        smb (SmbClient): Configured SMB client.
        config (SmbConfig): Resolved SMB backup directory.

    RETURNS:
        Path | None: Local path to the downloaded APK, or None if no base
        image has been published to SMB.
    """
    base_smb_remote = f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/{_BASE_APK_NAME}"
    local_apk = ws / _BASE_APK_NAME
    try:
        smb.download_file(base_smb_remote, str(local_apk))
    except OSError:
        return None
    return local_apk


def _base_apk_version(smb: SmbClient, config: SmbConfig) -> str:
    """RETURNS: str: Kodi version recorded for the published base APK, or `""`.

    Written by the fetch-base job alongside the APK; read here so deploy can
    tell whether pushing it would actually change anything.
    """
    try:
        meta = json.loads(smb.read_text(f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/kodi-latest.meta.json"))
    except Exception as exc:
        LOGGER.debug("No readable base APK meta: %s", exc)
        return ""
    return str(meta.get("kodi_version") or "")


def _install_base_apk(
    handle: OperationHandle,
    ws: Path,
    smb: SmbClient,
    config: SmbConfig,
    adb: AdbClient,
    base_apk_local: Path | None,
) -> None:
    """Install the shared base Kodi APK, unless the device already runs it.

    The version check exists because this used to push the APK on *every*
    deploy regardless of what was installed — roughly 100MB over ADB each
    time, for no change in the common case where the whole fleet is already
    on the base version. On a device with marginal wifi that push exceeded
    the 180s transfer timeout and failed the entire deploy before any config
    was written (observed on a real device pushing Kodi 21.3 over an
    already-installed Kodi 21.3).
    """
    installed = collect_kodi_metadata(adb).get("kodi_version", "")
    base_version = _base_apk_version(smb, config)
    if installed and base_version and installed == base_version:
        handle.log(f"Kodi {installed} already installed, skipping APK push")
        return

    if base_apk_local is None:
        base_apk_local = resolve_base_apk(ws, smb, config)
    if base_apk_local is None:
        handle.log("No base APK found on SMB, skipping Kodi install")
        return

    detail = f"{installed or 'unknown'} -> {base_version or 'unknown'}"
    handle.log(f"Installing base Kodi APK ({detail})...")
    adb.push_file(str(base_apk_local), _DEVICE_APK_PATH)
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

"""Deploy job: push a built profile to a device and extract it there.

Deploy does no profile shaping — pruning, settings overrides, hub layout and
view-type fixes all happen once in `jobs.build`. What is left here is only
what genuinely varies per device: the installed Kodi version, the transfer
itself, and that device's own display calibration.

The transfer is a single archive extracted on-device rather than a per-file
push. The per-file sync it replaces cost one ADB round-trip per file (plus a
`mkdir` per file, plus one `rm` per stale remote file); a profile with
thousands of cached files reliably stalled `adbd` partway through.
"""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path

from .._adb import AdbClient, AdbKeyStore
from .._artifacts import BUILD_DEVICE_DIR, GOLD_DEVICE_DIR, BackupRef
from .._device_settings import apply_device_settings, validate_device_settings
from .._kodi import check_device_online, collect_kodi_metadata
from .._smb import SmbClient
from ..const import REMOTE_KODI_PATH
from ..device_store import DeviceStore
from ..models import SmbConfig
from ..operations import OperationHandle
from .build import PROFILE_FOLDERS
from .display import patch_display_settings, validate_display_settings

LOGGER = logging.getLogger(__name__)

_BASE_APK_NAME = "kodi-latest.apk"
_DEVICE_APK_PATH = "/sdcard/kodi-latest.apk"
_DEVICE_STAGE_DIR = "/sdcard"

# The archive is pushed compressed, decompressed in place, then extracted —
# so at peak the device needs room for all three at once.
_DISK_HEADROOM = 3.0

# Floor throughput for on-device gunzip/untar. A Fire Stick writing thousands
# of small files to /sdcard is far slower than the flat shell timeout assumes.
_MIN_UNPACK_BYTES_PER_S = 1_000_000.0


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
    """Deploy a built profile (or the latest build) to a device.

    **PARAMETERS:**
        `handle` (OperationHandle): Handle to log through and check cancellation.  <br>
        `ws` (Path): Per-operation staging directory.  <br>
        `ip` (str): Target device IP.  <br>
        `backup_name` (str | None): Validated ``builds/filename`` reference, or ``None`` to deploy the most recent build.  <br>
        `devices` (DeviceStore): Source of this device's `Device.display` calibration and `Device.settings` overrides, both reapplied after extraction since the build's own `guisettings.xml` overwrites them.  <br>
        `adb_keys` (AdbKeyStore): Shared ADB signer cache.  <br>
        `smb` (SmbClient): Configured SMB client.  <br>
        `config` (SmbConfig): Resolved SMB backup directory.  <br>
        `base_apk_local` (Path | None, optional): Pre-downloaded base APK to install. Pass this when deploying to multiple devices in one run (see `resolve_base_apk`) so the same file isn't re-fetched from SMB once per device. Defaults to ``None``, in which case this job resolves it itself.  <br>

    **RETURNS:**
        `str`: Human-readable result summary.  <br>

    **RAISES:**
        `RuntimeError`: If the device is offline, no build can be found, or the device lacks the free space to extract one.  <br>
        `ValueError`: If `backup_name` points outside the builds directory.  <br>
    """
    handle.log(f"Prepping {ip}...")
    handle.log("Checking device connectivity...")
    if not check_device_online(ip):
        raise RuntimeError(f"Device {ip} offline")

    ref = _resolve_build_ref(handle, backup_name, smb, config)

    handle.log(f"Downloading {ref.wire()} from SMB...")
    local_tar = ref.local_path(ws)
    smb.download_file(ref.smb_remote(config.smb_backup_dir), str(local_tar))
    archive_size = local_tar.stat().st_size

    with AdbClient(ip, adb_keys) as adb:
        _install_base_apk(handle, ws, smb, config, adb, base_apk_local)

        handle.check_cancelled()
        _check_free_space(adb, archive_size)

        handle.log(f"Pushing {ref.filename} ({archive_size // (1024 * 1024)}MB) to {ip}...")
        adb.shell_ok("am force-stop org.xbmc.kodi")
        device_tar = f"{_DEVICE_STAGE_DIR}/{ref.filename}"
        adb.shell_ok(f"rm -f {shlex.quote(device_tar)} {shlex.quote(device_tar.removesuffix('.gz'))}")
        adb.push_file(str(local_tar), device_tar)

        handle.check_cancelled()
        handle.log("Extracting on device...")
        _extract_on_device(adb, device_tar, _unpack_timeout(archive_size, adb_keys.transfer_timeout_s))
        _verify_extracted(adb)
        handle.log("Profile extracted")

        handle.check_cancelled()
        _apply_device_overrides(handle, adb, devices, ip)

    handle.log(f"Deployment finished for {ip}")
    return f"Deployed {ref.filename} to {ip}"


def _apply_device_overrides(handle: OperationHandle, adb: AdbClient, devices: DeviceStore, ip: str) -> None:
    """Reapply everything that is specific to this device, not to the build.

    The build's own `guisettings.xml` overwrote whatever was calibrated here,
    so this has to run after extraction. An invalid entry is logged and
    skipped rather than failing a deploy that otherwise succeeded — the
    profile is already on the device by this point.
    """
    dev = devices.get_by_ip(ip)
    if not dev:
        return

    if dev.display:
        try:
            validate_display_settings(dev.display)
        except ValueError as exc:
            handle.log(f"Stored display calibration invalid, skipping: {exc}")
        else:
            handle.log("Reapplying stored display calibration...")
            patch_display_settings(adb, dev.display, handle)

    if dev.settings:
        try:
            validated = validate_device_settings(dev.settings)
        except ValueError as exc:
            handle.log(f"Per-device settings invalid, skipping: {exc}")
            return
        handle.log("Applying per-device setting overrides...")
        for change in apply_device_settings(adb, validated):
            handle.log(f"  {change}")


def _extract_on_device(adb: AdbClient, device_tar: str, timeout_s: float) -> None:
    """Replace the device's Kodi profile folders with the pushed archive.

    Decompression and extraction are separate commands (`gzip -d`, then plain
    `tar xf`) rather than `tar xzf`: toybox's built-in `-z` handling is
    unreliable on this Fire OS build — see the capture job's matching split
    and the `gotcha_toybox_tar_gzip_truncation` memory.
    """
    plain_tar = device_tar.removesuffix(".gz")
    adb.shell(f"gzip -d {shlex.quote(device_tar)}", timeout_s=timeout_s)

    for folder in PROFILE_FOLDERS:
        adb.shell_ok(f"rm -rf {shlex.quote(f'{REMOTE_KODI_PATH}/{folder}')}")
    adb.shell(f"mkdir -p {shlex.quote(REMOTE_KODI_PATH)}")

    adb.shell(f"tar xf {shlex.quote(plain_tar)} -C {shlex.quote(REMOTE_KODI_PATH)}", timeout_s=timeout_s)
    adb.shell_ok(f"rm -f {shlex.quote(plain_tar)}")


def _verify_extracted(adb: AdbClient) -> None:
    """Fail loudly if extraction left the profile unusable.

    `tar` exiting cleanly is not proof the profile arrived — a truncated
    archive can extract "successfully" into a half-populated tree, which Kodi
    then starts against and rebuilds from scratch.

    **RAISES:**
        `RuntimeError`: If the core profile folders are missing or empty.  <br>
    """
    for folder in ("addons", "userdata"):
        remote = f"{REMOTE_KODI_PATH}/{folder}"
        listing = adb.shell_ok(f"ls {shlex.quote(remote)} | head -1")
        if not listing.strip():
            raise RuntimeError(f"Deploy verification failed: {remote} is missing or empty")


def _unpack_timeout(archive_size: int, floor_s: float) -> float:
    """Scale the shell timeout for the on-device gunzip/untar steps by archive size."""
    return max(floor_s, archive_size / _MIN_UNPACK_BYTES_PER_S)


def _check_free_space(adb: AdbClient, archive_size: int) -> None:
    """Bail out before pushing an archive the device has no room to extract.

    **RAISES:**
        `RuntimeError`: If free space won't cover the archive plus its extracted contents.  <br>
    """
    free = adb.free_bytes(_DEVICE_STAGE_DIR)
    needed = int(archive_size * _DISK_HEADROOM)
    if free and free < needed:
        raise RuntimeError(f"Not enough free space: need ~{needed // (1024 * 1024)}MB, {free // (1024 * 1024)}MB available")


def resolve_base_apk(ws: Path, smb: SmbClient, config: SmbConfig) -> Path | None:
    """Download the shared base Kodi APK from SMB, if one has been published.

    Split out from `_install_base_apk` so a batch deploy (`cli.py`'s
    `--batch`, or any future fleet-wide caller) can resolve it once and pass
    the same local file into every device's `run_deploy` call, instead of
    downloading the same ~30-80MB file once per device.

    **PARAMETERS:**
        `ws` (Path): Staging directory to download into.  <br>
        `smb` (SmbClient): Configured SMB client.  <br>
        `config` (SmbConfig): Resolved SMB backup directory.  <br>

    **RETURNS:**
        `Path | None`: Local path to the downloaded APK, or ``None`` if no base image has been published to SMB.  <br>
    """
    base_smb_remote = f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}/{_BASE_APK_NAME}"
    local_apk = ws / _BASE_APK_NAME
    try:
        smb.download_file(base_smb_remote, str(local_apk))
    except OSError:
        return None
    return local_apk


def _base_apk_version(smb: SmbClient, config: SmbConfig) -> str:
    """Read the Kodi version recorded for the published base APK.

    Written by the fetch-base job alongside the APK; read here so deploy can
    tell whether pushing it would actually change anything.

    **RETURNS:**
        `str`: The recorded Kodi version, or ``""`` if no readable metadata exists.  <br>
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
    on the base version.
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


def _resolve_build_ref(handle: OperationHandle, backup_name: str | None, smb: SmbClient, config: SmbConfig) -> BackupRef:
    """Resolve which build to deploy, defaulting to the most recent one.

    **RETURNS:**
        `BackupRef`: The build to deploy.  <br>

    **RAISES:**
        `ValueError`: If `backup_name` refers to something outside ``builds/`` — deploy only ships built profiles, raw captures go through `jobs.build` first.  <br>
        `RuntimeError`: If no build has been published yet.  <br>
    """
    if backup_name:
        ref = BackupRef.parse(backup_name)
        if ref.device_dir != BUILD_DEVICE_DIR:
            raise ValueError(f"{backup_name!r} is not a build — run a build first, then deploy it")
        return ref

    handle.log("Finding latest build...")
    candidates: list[str] = []
    try:
        for entry in smb.scandir(f"{config.smb_backup_dir}/{BUILD_DEVICE_DIR}"):
            if entry.name.endswith(".tar.gz"):
                candidates.append(entry.name)
    except Exception as exc:
        LOGGER.debug("SMB scandir failed for %s: %s", BUILD_DEVICE_DIR, exc)
    if not candidates:
        raise RuntimeError("No builds found — run a build first")
    return BackupRef(device_dir=BUILD_DEVICE_DIR, filename=sorted(candidates)[-1])

"""FleetService: the one home for fleet-management business logic.

Replaces sixteen websocket handlers that each inlined busy-checks, op-id
minting, and thread spawning. `ws_api.py` becomes a thin protocol adapter;
this module is where "what a capture/deploy/maintain/scan actually is"
lives, independent of the websocket transport.
"""
from __future__ import annotations

import functools
import json
import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ._adb import AdbClient, AdbKeyStore, AdbShellRunner
from ._artifacts import GOLD_DEVICE_DIR, BackupRef, validate_backup_name
from ._kodi import check_device_online, collect_kodi_metadata
from ._smb import SmbClient
from .device_store import DeviceStore
from .jobs import capture as _capture_job
from .jobs import deploy as _deploy_job
from .jobs import display as _display_job
from .jobs import fetch_base as _fetch_base_job
from .jobs import maintain as _maintain_job
from .jobs import scan as _scan_job
from .jobs._runner import run_job
from .models import OperationStatus, OperationType, SmbConfig
from .operations import OperationRegistry

LOGGER = logging.getLogger(__name__)

_MAX_WORKERS = 8


class FleetService:
    """Fleet-management operations: devices, backups, and background jobs.

    PARAMETERS:
        config (SmbConfig): Resolved SMB configuration.
        devices (DeviceStore): Device repository.
        operations (OperationRegistry): Operation tracker.
        smb (SmbClient): Configured SMB client.
        adb_keys (AdbKeyStore): Shared ADB signer cache.
        staging_root (Path): Parent directory for per-job staging dirs.
    """

    def __init__(
        self,
        config: SmbConfig,
        devices: DeviceStore,
        operations: OperationRegistry,
        smb: SmbClient,
        adb_keys: AdbKeyStore,
        staging_root: Path,
    ) -> None:
        self._config = config
        self._devices = devices
        self._operations = operations
        self._smb = smb
        self._adb_keys = adb_keys
        self._staging_root = staging_root
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="fire_tools")

    def shutdown(self) -> None:
        """Stop accepting new jobs. Does not cancel jobs already running."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- Devices -----------------------------------------------------------

    def list_devices(self) -> list[dict[str, Any]]:
        """RETURNS: list[dict]: Known devices, in the wire shape the frontend expects."""
        return [
            {
                "ip": d.ip, "name": d.name, "model": d.model,
                "serial": d.serial, "mac": d.mac, "display": d.display,
            }
            for d in self._devices.list()
        ]

    def check_device(self, ip: str) -> tuple[bool, dict[str, str]]:
        """Probe whether a device is online and, if so, its Kodi metadata.

        RETURNS:
            tuple[bool, dict[str, str]]: `(online, metadata)`.
        """
        online = check_device_online(ip)
        if not online:
            return False, {}
        try:
            with AdbClient(ip, self._adb_keys) as adb:
                meta = collect_kodi_metadata(adb)
        except Exception as exc:
            LOGGER.warning("Failed to fetch metadata for %s: %s", ip, exc)
            meta = {}
        return True, meta

    def is_known_device(self, ip: str) -> bool:
        """RETURNS: bool: Whether `ip` is a device already in the store."""
        return self._devices.get_by_ip(ip) is not None

    # -- Scan ----------------------------------------------------------------

    def start_scan(self, subnet: str) -> str:
        """Start a network scan for the given subnet.

        RETURNS:
            str: The new operation id.
        """
        op_id = f"scan_{int(time.time())}"
        self._operations.start(op_id, OperationType.SCAN, subnet)
        adb_runner = AdbShellRunner(self._adb_keys)
        job = functools.partial(_scan_job.run_scan, subnet=subnet, devices=self._devices, adb_runner=adb_runner)
        self._dispatch(op_id, job)
        return op_id

    # -- Capture / Deploy / Maintain -----------------------------------------

    def start_capture(self, ip: str, backup_name: str | None) -> str:
        """Start a capture job for `ip`.

        RETURNS:
            str: The new operation id.

        RAISES:
            ValueError: If `ip` already has a running operation.
        """
        self._require_idle(ip)
        if backup_name:
            validate_backup_name(backup_name)
        op_type = OperationType.CAPTURE_GOLD if backup_name and backup_name.startswith("gold-") else OperationType.CAPTURE
        op_id = f"capture_{ip}_{int(time.time())}"
        self._operations.start(op_id, op_type, ip)
        job = functools.partial(
            _capture_job.run_capture, ip=ip, backup_name=backup_name,
            devices=self._devices, adb_keys=self._adb_keys, smb=self._smb, config=self._config,
        )
        self._dispatch(op_id, job)
        return op_id

    def start_deploy(self, ip: str, backup_name: str | None) -> str:
        """Start a deploy job for `ip`.

        RETURNS:
            str: The new operation id.

        RAISES:
            ValueError: If `ip` already has a running operation.
        """
        self._require_idle(ip)
        if backup_name:
            BackupRef.parse(backup_name)
        op_id = f"deploy_{ip}_{int(time.time())}"
        self._operations.start(op_id, OperationType.DEPLOY, ip)
        job = functools.partial(
            _deploy_job.run_deploy, ip=ip, backup_name=backup_name,
            devices=self._devices, adb_keys=self._adb_keys, smb=self._smb, config=self._config,
        )
        self._dispatch(op_id, job)
        return op_id

    def start_maintain(self, ip: str) -> str:
        """Start a maintenance job for `ip`.

        RETURNS:
            str: The new operation id.

        RAISES:
            ValueError: If `ip` already has a running operation.
        """
        self._require_idle(ip)
        op_id = f"maintain_{ip}_{int(time.time())}"
        self._operations.start(op_id, OperationType.MAINTAIN, ip)
        job = functools.partial(_maintain_job.run_maintain, ip=ip, adb_keys=self._adb_keys)
        self._dispatch(op_id, job)
        return op_id

    def apply_display(self, ip: str, display_settings: dict[str, Any]) -> str:
        """Start a job patching resolution/overscan calibration onto a device.

        RETURNS:
            str: The new operation id.

        RAISES:
            ValueError: If `ip` already has a running operation, or
                `display_settings` has no recognized fields.
        """
        self._require_idle(ip)
        op_id = f"display_{ip}_{int(time.time())}"
        self._operations.start(op_id, OperationType.DISPLAY, ip)
        job = functools.partial(
            _display_job.run_apply_display, ip=ip, display_settings=display_settings, adb_keys=self._adb_keys,
        )
        self._dispatch(op_id, job)
        return op_id

    def start_capture_base(self) -> str:
        """Start a job to fetch and publish the latest stable Kodi base image.

        RETURNS:
            str: The new operation id.
        """
        op_id = f"base_{int(time.time())}"
        self._operations.start(op_id, OperationType.FETCH, "")
        job = functools.partial(_fetch_base_job.run_fetch_base, smb=self._smb, config=self._config)
        self._dispatch(op_id, job)
        return op_id

    def deploy_all(self) -> list[str]:
        """Deploy each idle known device's latest backup.

        RETURNS:
            list[str]: Operation ids started (devices already busy are skipped).
        """
        op_ids = []
        for dev in self._devices.list():
            if self._operations.has_running(dev.ip):
                continue
            op_ids.append(self.start_deploy(dev.ip, None))
        return op_ids

    def maintain_all(self) -> list[str]:
        """Run maintenance on each idle known device.

        RETURNS:
            list[str]: Operation ids started (devices already busy are skipped).
        """
        op_ids = []
        for dev in self._devices.list():
            if self._operations.has_running(dev.ip):
                continue
            op_ids.append(self.start_maintain(dev.ip))
        return op_ids

    # -- Operations -----------------------------------------------------------

    def get_operation(self, op_id: str) -> dict[str, Any] | None:
        """RETURNS: dict | None: Snapshot of the operation, if it exists."""
        op = self._operations.get(op_id)
        return op.snapshot() if op else None

    def list_operations(self) -> dict[str, dict[str, Any]]:
        """RETURNS: dict[str, dict]: Snapshots of every tracked operation."""
        return self._operations.all_snapshots()

    def cancel_operation(self, op_id: str) -> bool:
        """RETURNS: bool: False if `op_id` is unknown or not running."""
        return self._operations.request_cancel(op_id)

    def rerun_operation(self, op_id: str) -> str | None:
        """Start a fresh operation of the same kind/target as a finished one.

        Mints a new operation id rather than mutating the original record,
        so the prior attempt's history is preserved.

        RETURNS:
            str | None: The new operation id, or None if `op_id` is unknown
            or still running.
        """
        op = self._operations.get(op_id)
        if not op or op.status == OperationStatus.RUNNING:
            return None
        dispatch = {
            OperationType.CAPTURE: lambda: self.start_capture(op.device_ip, None),
            OperationType.CAPTURE_GOLD: lambda: self.start_capture(op.device_ip, None),
            OperationType.DEPLOY: lambda: self.start_deploy(op.device_ip, None),
            OperationType.MAINTAIN: lambda: self.start_maintain(op.device_ip),
        }.get(op.type)
        return dispatch() if dispatch else None

    # -- Backups / base image --------------------------------------------------

    def list_backups(self) -> list[dict[str, Any]]:
        """RETURNS: list[dict]: All backups found on the SMB share, newest first."""
        if not self._config.has_smb:
            return []
        backups: list[dict[str, Any]] = []
        try:
            for entry in self._smb.scandir(self._config.smb_backup_dir):
                if not entry.is_dir():
                    continue
                backups.extend(self._list_backups_in(entry.name))
        except Exception as exc:
            LOGGER.warning("SMB list failed: %s", exc)
        backups.sort(key=lambda b: b.get("date", ""), reverse=True)
        return backups

    def _list_backups_in(self, device_dir: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            for file_entry in self._smb.scandir(f"{self._config.smb_backup_dir}/{device_dir}"):
                if not file_entry.name.endswith(".tar.gz"):
                    continue
                ref = BackupRef(device_dir=device_dir, filename=file_entry.name)
                meta: dict[str, Any] = {}
                try:
                    meta = json.loads(self._smb.read_text(ref.smb_meta_remote(self._config.smb_backup_dir)))
                except Exception:
                    pass
                stat = file_entry.stat()
                result.append({
                    "filename": ref.wire(),
                    "device_name": meta.get("device_name") or device_dir,
                    "device_mac": meta.get("device_mac", ""),
                    "size": str(meta.get("size") or stat.st_size or "?"),
                    "date": meta.get("captured_at", ""),
                    "kodi_version": meta.get("kodi_version", ""),
                    "arctic_fuse": meta.get("arctic_fuse", ""),
                    "android_version": meta.get("android_version", ""),
                })
        except Exception:
            pass
        return result

    def get_base_info(self) -> dict[str, Any]:
        """RETURNS: dict: Current gold Kodi base image version, if known."""
        result: dict[str, Any] = {"version": None, "update_available": False, "latest_version": None}
        try:
            meta = json.loads(self._smb.read_text(f"{self._config.smb_backup_dir}/{GOLD_DEVICE_DIR}/kodi-latest.meta.json"))
            result["version"] = meta.get("kodi_version")
        except Exception:
            pass
        return result

    def check_update(self) -> dict[str, Any]:
        """Check the current gold base image against the latest xbmc/xbmc release.

        RETURNS:
            dict: `{version, update_available, latest_version}`.
        """
        current = None
        try:
            meta = json.loads(self._smb.read_text(f"{self._config.smb_backup_dir}/{GOLD_DEVICE_DIR}/kodi-latest.meta.json"))
            current = meta.get("kodi_version", "")
        except Exception:
            pass
        result: dict[str, Any] = {"version": current, "update_available": False, "latest_version": None}
        try:
            url = "https://api.github.com/repos/xbmc/xbmc/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant/Firetools"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read())
            latest = release.get("tag_name", "").lstrip("v")
            latest_match = re.search(r"(\d+(?:\.\d+)*)", latest)
            current_match = re.search(r"(\d+(?:\.\d+)*)", current or "")
            latest_ver = latest_match.group(1) if latest_match else latest
            current_ver = current_match.group(1) if current_match else current
            if latest and latest_ver != current_ver:
                result["update_available"] = True
                result["latest_version"] = latest
        except Exception as exc:
            LOGGER.warning("Update check failed: %s", exc)
        return result

    # -- Internal --------------------------------------------------------------

    def _require_idle(self, ip: str) -> None:
        existing = self._operations.has_running(ip)
        if existing:
            raise ValueError(f"Device has running operation: {existing}")

    def _dispatch(self, op_id: str, job: Any) -> None:
        self._executor.submit(run_job, self._operations, self._staging_root, op_id, job)

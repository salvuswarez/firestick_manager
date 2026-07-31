"""Domain models: devices, SMB config, and operation tracking.

Deliberately free of any consumer-specific imports (no Home Assistant, no
click) so this package can be constructed and tested standalone, and used
identically from the CLI or from an HA integration wrapping it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .const import DEFAULT_SMB_BACKUP_DIR, DEFAULT_SMB_HOST, DEFAULT_SMB_SHARE


class Device(BaseModel):
    """A Fire TV device tracked in the device store (`devices.json`/`devices.yml`).

    PARAMETERS:
        ip (str): Current IPv4 address.
        mac (str): MAC address, lowercase colon-separated, or empty if unknown.
        name (str): Display name (may originate from ADB `device_name`).
        model (str): Android product model string.
        serial (str): ADB serial number.
        android_version (str): Android release string (e.g. "9").
        display (dict[str, Any]): Kodi resolution/overscan calibration —
            `{"resolution_index": int, "overscan": {"left": int, "top": int,
            "right": int, "bottom": int}}`, both optional. Captured live from
            the device by `jobs.capture` and reapplied by `jobs.deploy` after
            every sync; empty if never captured or calibrated.
    """

    model_config = ConfigDict(extra="ignore")

    ip: str
    mac: str = ""
    name: str = "Unknown"
    model: str = "Unknown"
    serial: str = ""
    android_version: str = ""
    display: dict[str, Any] = Field(default_factory=dict)


class BackupMeta(BaseModel):
    """Sidecar `.meta.json` written alongside every backup/base-image archive.

    PARAMETERS:
        device_name (str): Device name at capture time, or "gold"/"base" for
            shared images.
        device_mac (str): Device MAC at capture time.
        device_ip (str): Device IP at capture time.
        captured_at (str): ISO-8601 capture timestamp.
        kodi_version (str): Kodi `versionName` at capture time.
        arctic_fuse (str): Arctic Fuse skin version, if detected.
        android_version (str): Android release string.
        size (int): Archive size in bytes.
    """

    model_config = ConfigDict(extra="ignore")

    device_name: str = ""
    device_mac: str = ""
    device_ip: str = ""
    captured_at: str = ""
    kodi_version: str = ""
    arctic_fuse: str = ""
    android_version: str = ""
    size: int = 0


@dataclass(frozen=True, slots=True)
class SmbConfig:
    """Resolved SMB (router-USB / NAS) configuration.

    Consumer-agnostic: build it from a plain mapping of lowercase keys
    (`smb_host`, `smb_share`, `smb_user`, `smb_pass`, `smb_backup_dir`) —
    the CLI builds that mapping from `.env`, an HA integration builds it
    from `entry.data` merged with `entry.options`.

    PARAMETERS:
        smb_host (str): SMB server hostname/IP.
        smb_share (str): SMB share name.
        smb_user (str): SMB username; empty means SMB is not configured.
        smb_pass (str): SMB password.
        smb_backup_dir (str): Backup root directory on the share.
    """

    smb_host: str = DEFAULT_SMB_HOST
    smb_share: str = DEFAULT_SMB_SHARE
    smb_user: str = ""
    smb_pass: str = ""
    smb_backup_dir: str = DEFAULT_SMB_BACKUP_DIR

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> SmbConfig:
        """Build config from a base mapping, with `overrides` taking precedence.

        PARAMETERS:
            data (Mapping[str, Any]): Base config (e.g. `entry.data`, or a
                mapping built from `.env`), keyed by `smb_host`/`smb_share`/
                `smb_user`/`smb_pass`/`smb_backup_dir`.
            overrides (Mapping[str, Any] | None): Values that win over `data`
                (e.g. `entry.options`), same keys.

        RETURNS:
            SmbConfig: Resolved config.
        """
        merged: dict[str, Any] = dict(data)
        merged.update(overrides or {})
        return cls(
            smb_host=merged.get("smb_host", DEFAULT_SMB_HOST),
            smb_share=merged.get("smb_share", DEFAULT_SMB_SHARE),
            smb_user=merged.get("smb_user", ""),
            smb_pass=merged.get("smb_pass", ""),
            smb_backup_dir=merged.get("smb_backup_dir", DEFAULT_SMB_BACKUP_DIR),
        )

    @property
    def has_smb(self) -> bool:
        """RETURNS: bool: Whether SMB credentials are configured."""
        return bool(self.smb_user)


class OperationStatus(str, Enum):
    """Lifecycle states for a tracked background operation."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationType(str, Enum):
    """Kinds of background operation the fleet service can run."""

    CAPTURE = "capture"
    CAPTURE_GOLD = "capture_gold"
    DEPLOY = "deploy"
    MAINTAIN = "maintain"
    SCAN = "scan"
    FETCH = "fetch"
    DISPLAY = "display"


@dataclass(slots=True)
class Operation:
    """Mutable record of one background operation.

    PARAMETERS:
        id (str): Operation id, e.g. `capture_192.168.50.10_1699999999`.
        type (OperationType): Kind of operation.
        device_ip (str): Target device IP, or the scanned subnet for a scan,
            or "" for fleet-wide operations.
        status (OperationStatus): Current lifecycle state.
        logs (list[dict[str, str]]): Ordered `{time, message}` log entries.
        started_at (str): ISO-8601 start timestamp.
        completed_at (str | None): ISO-8601 completion timestamp, if finished.
        result (str | None): Human-readable result/error summary.
    """

    id: str
    type: OperationType
    device_ip: str
    status: OperationStatus = OperationStatus.RUNNING
    logs: list[dict[str, str]] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None
    result: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """Return an immutable, JSON-serializable copy of this operation.

        RETURNS:
            dict[str, Any]: Copy of this operation with `logs` shallow-copied,
            safe to serialize even while a worker thread keeps appending.
        """
        return {
            "id": self.id,
            "type": self.type.value,
            "device_ip": self.device_ip,
            "status": self.status.value,
            "logs": list(self.logs),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
        }

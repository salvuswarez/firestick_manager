"""Repository for the known device fleet (`devices.json` or `devices.yml`).

Owns the one lock around read-modify-write so a scan completing mid-deploy
can no longer lose an update, and the one atomic-write implementation
(unique temp file, not a fixed shared name). Format is chosen by the file
extension: `.yml`/`.yaml` for the human-edited CLI inventory, JSON
otherwise (e.g. an HA integration's internal store).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path

from ._merge import ReconcileResult, reconcile
from .models import Device

LOGGER = logging.getLogger(__name__)

_YAML_SUFFIXES = (".yml", ".yaml")


class DeviceStore:
    """Loads, persists, and reconciles the device fleet.

    PARAMETERS:
        path (Path): Location of the device inventory file. Should live
            outside any git-tracked directory if it will accumulate
            scan-discovered MAC addresses (e.g.
            `hass.config.path("firetools_devices.json")`, or a gitignored
            `resources/devices.yml` for the CLI).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._is_yaml = path.suffix.lower() in _YAML_SUFFIXES
        self._lock = threading.Lock()

    def list(self) -> list[Device]:
        """RETURNS: list[Device]: All known devices."""
        with self._lock:
            return self._load()

    def get_by_ip(self, ip: str) -> Device | None:
        """RETURNS: Device | None: The device at `ip`, if known."""
        with self._lock:
            return next((d for d in self._load() if d.ip == ip), None)

    def reconcile(self, discovered: list[Device]) -> ReconcileResult:
        """Merge freshly scanned devices into the store, under the write lock.

        PARAMETERS:
            discovered (list[Device]): Devices found by a scan.

        RETURNS:
            ReconcileResult: The merged list plus added/updated counts.
        """
        with self._lock:
            existing = self._load()
            result = reconcile(existing, discovered)
            self._save(result.devices)
            return result

    def _load(self) -> list[Device]:
        if not self._path.exists():
            return []
        with open(self._path, encoding="utf-8") as f:
            if self._is_yaml:
                import yaml

                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        if isinstance(data, dict) and "devices" in data:
            return [Device.model_validate(raw) for raw in data["devices"]]
        return []

    def _save(self, devices: list[Device]) -> None:
        tmp_path = self._path.with_name(f"{self._path.name}.{uuid.uuid4().hex}.tmp")
        payload = {"devices": [d.model_dump() for d in devices]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            if self._is_yaml:
                import yaml

                yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(self._path)
        LOGGER.info("Saved %d devices to %s", len(devices), self._path)

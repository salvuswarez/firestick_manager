"""Scan job: sweep a subnet for ADB-reachable devices and merge into the fleet."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..device_store import DeviceStore
from ..models import Device
from ..operations import OperationHandle
from ..scanner import Scanner


def run_scan(
    handle: OperationHandle,
    ws: Path,
    *,
    subnet: str,
    devices: DeviceStore,
    adb_runner: Callable[[str, str], str],
) -> str:
    """Ping-sweep `subnet`, probe responders via ADB, and reconcile into the store.

    PARAMETERS:
        handle (OperationHandle): Handle to log through and check cancellation.
        ws (Path): Per-operation staging directory (unused by this job).
        subnet (str): Validated three-octet subnet prefix (e.g. "192.168.50").
        devices (DeviceStore): Device repository to reconcile results into.
        adb_runner (Callable[[str, str], str]): `(ip, cmd) -> str` ADB runner
            passed through to `Scanner`.

    RETURNS:
        str: Human-readable summary of devices added/updated.
    """
    handle.log(f"Scanning subnet {subnet}.0/24")
    scanner = Scanner(subnet, adb_runner=adb_runner)
    discovered_raw = scanner.scan()
    handle.log(f"Discovered {len(discovered_raw)} active ADB hosts")

    handle.check_cancelled()
    discovered = [Device.model_validate(raw) for raw in discovered_raw]
    result = devices.reconcile(discovered)
    for dev in discovered:
        handle.log(f"Reconciled {dev.name} ({dev.ip})")

    summary = f"Added {result.added}, updated {result.updated}, total {len(result.devices)}"
    handle.log(f"Scan complete: {summary}")
    return summary

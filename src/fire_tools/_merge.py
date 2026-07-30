"""Pure device-list reconciliation (no I/O) for network scan results.

Extracted out of the scan task so the mac -> serial -> ip matching logic is
testable as plain data in, data out, instead of only reachable by running a
live ping sweep against real hardware.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Device


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    """Outcome of merging freshly discovered devices into the known fleet.

    PARAMETERS:
        devices (list[Device]): Full merged device list.
        added (int): Count of newly discovered devices.
        updated (int): Count of existing devices refreshed by this scan.
    """

    devices: list[Device]
    added: int
    updated: int


def reconcile(existing: list[Device], discovered: list[Device]) -> ReconcileResult:
    """Merge scan results into the known device list.

    Matches each discovered device to an existing one by MAC, then serial,
    then IP (in that order of preference), and updates in place; anything
    unmatched is added as a new device.

    PARAMETERS:
        existing (list[Device]): Previously known devices.
        discovered (list[Device]): Devices found by this scan.

    RETURNS:
        ReconcileResult: Merged list plus added/updated counts.
    """
    merged = [d.model_copy() for d in existing]
    added = 0
    updated = 0

    for disc in discovered:
        match: Device | None = None
        if disc.mac:
            match = next((d for d in merged if d.mac and d.mac.lower() == disc.mac.lower()), None)
        if match is None and disc.serial:
            match = next((d for d in merged if d.serial == disc.serial), None)
        if match is None:
            match = next((d for d in merged if d.ip == disc.ip), None)

        if match is not None:
            match.ip = disc.ip
            match.mac = disc.mac or match.mac
            match.name = disc.name or match.name
            match.model = disc.model or match.model
            match.serial = disc.serial or match.serial
            match.android_version = disc.android_version or match.android_version
            updated += 1
        else:
            merged.append(disc)
            added += 1

    return ReconcileResult(devices=merged, added=added, updated=updated)

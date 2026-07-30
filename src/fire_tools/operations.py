"""Operation tracking: registry, job-facing handle, and persistence sink.

Replaces five loose functions over a module-level dict. Fixes, relative to
the original `_operations`/`_op_*` globals:

- Cancel actually stops a job (jobs poll `OperationHandle.check_cancelled()`)
  instead of only flipping a status flag the worker thread later overwrites.
- Rerun mints a new operation id instead of mutating/destroying the
  original record in place.
- Log persistence is debounced instead of one SMB round-trip per line.
- Retention is bounded instead of growing for the process lifetime.
- Persisted records failing to parse are skipped, not trusted as-is.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from typing import Any, Protocol

from ._smb import SmbClient
from .models import Operation, OperationStatus, OperationType

LOGGER = logging.getLogger(__name__)

_MAX_OPERATIONS = 500
_FLUSH_EVERY_N_LOGS = 5


class OperationCancelled(Exception):
    """Raised inside a job body when its operation has been cancelled."""


class OperationSink(Protocol):
    """Persistence seam for operation records. Two adapters: SMB and null."""

    def save(self, op_id: str, snapshot: dict[str, Any]) -> None: ...

    def load_all(self) -> list[Operation]: ...


class NullOperationSink:
    """No-op sink used when SMB persistence is not configured."""

    def save(self, op_id: str, snapshot: dict[str, Any]) -> None:
        return None

    def load_all(self) -> list[Operation]:
        return []


class OperationHandle:
    """What a running job receives — logs, checks cancellation, completes.

    The job never touches the registry's internals directly, so it cannot
    accidentally read/write another operation's state.
    """

    def __init__(self, registry: "OperationRegistry", op_id: str) -> None:
        self.op_id = op_id
        self._registry = registry

    def log(self, message: str) -> None:
        """Append a log line, visible to the frontend on the next poll."""
        self._registry._log(self.op_id, message)

    def check_cancelled(self) -> None:
        """RAISES: OperationCancelled: If the user has requested cancellation."""
        if self._registry._is_cancelled(self.op_id):
            raise OperationCancelled(self.op_id)

    def complete(self, result: str | None) -> None:
        """Mark the operation completed successfully."""
        self._registry._finish(self.op_id, OperationStatus.COMPLETED, result)

    def fail(self, result: str) -> None:
        """Mark the operation failed."""
        self._registry._finish(self.op_id, OperationStatus.FAILED, result)

    def cancelled(self) -> None:
        """Mark the operation cancelled (job observed `check_cancelled()`)."""
        self._registry._finish(self.op_id, OperationStatus.CANCELLED, "Cancelled by user")


class OperationRegistry:
    """In-memory operation table with bounded retention and one owning lock.

    PARAMETERS:
        sink (OperationSink): Where operation records are persisted across
            restarts (SMB-backed, or a no-op sink if SMB isn't configured).
    """

    def __init__(self, sink: OperationSink) -> None:
        self._sink = sink
        self._lock = threading.Lock()
        self._ops: dict[str, Operation] = {}
        self._cancelled: set[str] = set()
        self._unflushed: dict[str, int] = {}

    def load_persisted(self) -> None:
        """Load operations persisted by a prior run.

        Any record still `running` when the process last stopped is marked
        `failed` — it cannot possibly still be in progress.
        """
        loaded = self._sink.load_all()
        with self._lock:
            for op in loaded:
                if op.status == OperationStatus.RUNNING:
                    op.status = OperationStatus.FAILED
                    op.result = "Interrupted (process restarted)"
                    op.completed_at = datetime.now().isoformat()
                self._ops[op.id] = op
        self._evict_if_needed()

    def start(self, op_id: str, op_type: OperationType, device_ip: str) -> OperationHandle:
        """Register a new running operation and return its handle.

        PARAMETERS:
            op_id (str): Unique operation id.
            op_type (OperationType): Kind of operation.
            device_ip (str): Target device IP (or subnet/"" as applicable).

        RETURNS:
            OperationHandle: Handle for the job to log/complete through.
        """
        with self._lock:
            self._ops[op_id] = Operation(id=op_id, type=op_type, device_ip=device_ip)
        self._evict_if_needed()
        return OperationHandle(self, op_id)

    def handle(self, op_id: str) -> OperationHandle:
        """RETURNS: OperationHandle: A handle for an already-started operation."""
        return OperationHandle(self, op_id)

    def get(self, op_id: str) -> Operation | None:
        """RETURNS: Operation | None: The operation, if it exists."""
        with self._lock:
            op = self._ops.get(op_id)
            return _copy(op) if op else None

    def all_snapshots(self) -> dict[str, dict[str, Any]]:
        """RETURNS: dict[str, dict]: Wire-safe snapshots of every tracked operation."""
        with self._lock:
            return {op_id: op.snapshot() for op_id, op in self._ops.items()}

    def has_running(self, device_ip: str) -> str | None:
        """RETURNS: str | None: The id of a running operation on `device_ip`, if any."""
        with self._lock:
            for op in self._ops.values():
                if op.device_ip == device_ip and op.status == OperationStatus.RUNNING:
                    return op.id
        return None

    def request_cancel(self, op_id: str) -> bool:
        """Request cancellation of a running operation.

        The operation is not marked cancelled here — the job itself observes
        `OperationHandle.check_cancelled()` at its next step boundary and
        reports its own outcome, so state never contradicts what the job
        actually did.

        RETURNS:
            bool: False if `op_id` is unknown or not running.
        """
        with self._lock:
            op = self._ops.get(op_id)
            if not op or op.status != OperationStatus.RUNNING:
                return False
            self._cancelled.add(op_id)
        return True

    def _log(self, op_id: str, message: str) -> None:
        with self._lock:
            op = self._ops.get(op_id)
            if not op:
                return
            op.logs.append({"time": datetime.now().isoformat(), "message": message})
            snapshot = op.snapshot()
            count = self._unflushed.get(op_id, 0) + 1
            flush = count >= _FLUSH_EVERY_N_LOGS
            self._unflushed[op_id] = 0 if flush else count
        if flush:
            self._sink.save(op_id, snapshot)

    def _is_cancelled(self, op_id: str) -> bool:
        with self._lock:
            return op_id in self._cancelled

    def _finish(self, op_id: str, status: OperationStatus, result: str | None) -> None:
        with self._lock:
            op = self._ops.get(op_id)
            if not op:
                return
            op.status = status
            op.result = result
            op.completed_at = datetime.now().isoformat()
            self._cancelled.discard(op_id)
            self._unflushed.pop(op_id, None)
            snapshot = op.snapshot()
        self._sink.save(op_id, snapshot)

    def _evict_if_needed(self) -> None:
        with self._lock:
            if len(self._ops) <= _MAX_OPERATIONS:
                return
            by_age = sorted(self._ops.values(), key=lambda o: o.started_at)
            for op in by_age[: len(self._ops) - _MAX_OPERATIONS]:
                if op.status != OperationStatus.RUNNING:
                    self._ops.pop(op.id, None)


def _copy(op: Operation) -> Operation:
    return Operation(
        id=op.id, type=op.type, device_ip=op.device_ip, status=op.status,
        logs=list(op.logs), started_at=op.started_at, completed_at=op.completed_at,
        result=op.result,
    )


def _operation_from_dict(raw: dict[str, Any]) -> Operation:
    """Reconstruct an `Operation` from a persisted JSON record.

    RAISES:
        ValueError | KeyError: If `raw` is missing required fields or has
            an unrecognized `type`/`status` — the caller should treat this
            as "skip this record", not trust it.
    """
    return Operation(
        id=raw["id"],
        type=OperationType(raw["type"]),
        device_ip=raw.get("device_ip", ""),
        status=OperationStatus(raw["status"]),
        logs=list(raw.get("logs", [])),
        started_at=raw.get("started_at", datetime.now().isoformat()),
        completed_at=raw.get("completed_at"),
        result=raw.get("result"),
    )


class SmbOperationSink:
    """Persists operation records as one JSON file per operation on SMB.

    PARAMETERS:
        smb (SmbClient): Configured SMB client.
        ops_dir (str): SMB-relative directory to store operation records in.
    """

    def __init__(self, smb: SmbClient, ops_dir: str) -> None:
        self._smb = smb
        self._ops_dir = ops_dir

    def save(self, op_id: str, snapshot: dict[str, Any]) -> None:
        """Write `snapshot` for `op_id`, logging (not raising) on failure."""
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", op_id)
        remote = f"{self._ops_dir}/{safe_id}.json"
        try:
            self._smb.makedirs(self._ops_dir)
            self._smb.write_text(remote, json.dumps(snapshot, indent=2, default=str))
        except Exception as exc:
            LOGGER.warning("SMB save failed for op %s: %s", op_id, exc)

    def load_all(self) -> list[Operation]:
        """RETURNS: list[Operation]: All previously persisted operations.

        Malformed records are skipped and logged at debug level rather than
        surfaced — a corrupt/foreign file on the share should not block
        startup or be trusted as a well-formed operation.
        """
        results: list[Operation] = []
        try:
            entries = list(self._smb.scandir(self._ops_dir))
        except Exception as exc:
            LOGGER.debug("SMB list failed for %s: %s", self._ops_dir, exc)
            return results
        for entry in entries:
            if not entry.name.endswith(".json"):
                continue
            try:
                raw = json.loads(self._smb.read_text(f"{self._ops_dir}/{entry.name}"))
                results.append(_operation_from_dict(raw))
            except Exception:
                LOGGER.debug("Skipping malformed persisted op %s", entry.name, exc_info=True)
        return results

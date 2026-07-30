"""Common envelope for every background job.

Collapses what used to be five duplicated try/except epilogues (and four
missing `finally` cleanups) into one place: every job gets its own
workspace, cleaned up on any exit path, and a uniform cancelled/failed/
completed outcome.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .._workspace import workspace
from ..operations import OperationCancelled, OperationHandle, OperationRegistry

LOGGER = logging.getLogger(__name__)

JobFn = Callable[[OperationHandle, Path], "str | None"]


def run_job(registry: OperationRegistry, staging_root: Path, op_id: str, fn: JobFn) -> None:
    """Run a job body under a per-operation workspace, in the calling thread.

    Intended to be the `target` of a `threading.Thread` (or submitted to an
    executor) — this function itself is synchronous/blocking.

    PARAMETERS:
        registry (OperationRegistry): Registry the operation was started in.
        staging_root (Path): Parent directory for this job's staging dir.
        op_id (str): The operation id (already started via `registry.start`).
        fn (JobFn): Job body: `(handle, workspace_dir) -> result | None`.
            Raise `OperationCancelled` (via `handle.check_cancelled()`) to
            stop early; any other exception is caught and reported as a
            failure with `LOGGER.exception` capturing the traceback.
    """
    handle = registry.handle(op_id)
    try:
        with workspace(staging_root, op_id) as ws:
            result = fn(handle, ws)
        handle.complete(result)
    except OperationCancelled:
        handle.cancelled()
    except Exception as exc:
        LOGGER.exception("Job %s failed", op_id)
        handle.fail(str(exc))

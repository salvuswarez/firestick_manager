"""Per-operation staging directories.

The original code shared one fixed `/tmp/firetools_staging` across every
job, so a fleet-wide "Deploy All" (one thread per device) had sibling
threads deleting each other's `kodi-latest.apk` / extracted backup mid-push.
Each job now gets its own directory, cleaned up when the job finishes.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def workspace(root: Path, op_id: str) -> Iterator[Path]:
    """Create a staging directory scoped to one operation.

    PARAMETERS:
        root (Path): Parent directory for all operation staging dirs
            (e.g. `hass.config.path("firetools_staging")`).
        op_id (str): Operation id, used as the directory name.

    YIELDS:
        Path: The per-operation staging directory. Removed on exit
        regardless of success or failure.
    """
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=f"{op_id}_", dir=str(root)))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

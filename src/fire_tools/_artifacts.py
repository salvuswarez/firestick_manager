"""Backup artifact naming and path conventions.

Single owner of "what a backup is called and where it lives" — capture,
deploy, and list_backups all speak `BackupRef` instead of re-deriving
filenames and SMB/local paths from string formatting in three places.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .const import ARCHIVE_ROOT

# Leading "." is allowed because capture's default backup name is
# ".kodi_<timestamp>" (matching the on-device .kodi/ directory convention);
# ".." traversal is rejected explicitly below rather than by the character
# class, since a leading-dot allowance would otherwise let it through.
_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9.][A-Za-z0-9._-]{0,63}$")
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _is_safe_segment(part: str) -> bool:
    return bool(_SAFE_PATH_SEGMENT.match(part)) and ".." not in part and part != "."


GOLD_DEVICE_DIR = "gold"

# Built, ready-to-deploy profiles live in their own SMB directory, separate
# from raw captures. A build archive is *flat* (`addons/`, `userdata/`,
# `media/` at the tar root, no `.kodi/` wrapper) so deploy can extract it
# straight into the device's Kodi directory with no path rewriting.
BUILD_DEVICE_DIR = "builds"


def sanitize_device_name(name: str) -> str:
    """Sanitize a device-supplied name for use as a filesystem/SMB path segment.

    Device names originate from ADB (`settings get global device_name`) on
    devices discovered over the LAN and must never be trusted as path input.

    PARAMETERS:
        name (str): Raw device name.

    RETURNS:
        str: A lowercase string containing only `[a-z0-9._-]`, capped at 48
        chars, or `"unknown"` if nothing safe remains.
    """
    cleaned = _UNSAFE_NAME_CHARS.sub("_", name.strip().lower()).strip("._")
    return cleaned[:48] or "unknown"


def validate_backup_name(name: str) -> str:
    """Validate a single-segment backup name (used when starting a capture).

    PARAMETERS:
        name (str): Candidate backup name from the websocket client.

    RETURNS:
        str: The validated name, unchanged.

    RAISES:
        ValueError: If empty, contains anything outside `[A-Za-z0-9._-]`,
            or contains `..`.
    """
    if not name or not _is_safe_segment(name):
        raise ValueError(f"Invalid backup name: {name!r}")
    return name


@dataclass(frozen=True, slots=True)
class BackupRef:
    """A reference to one backup archive: `device_dir/filename.tar.gz`.

    PARAMETERS:
        device_dir (str): Sanitized device name, or `"gold"` for the shared
            base image.
        filename (str): Archive filename, e.g. `.kodi_20260729_101500.tar.gz`.
    """

    device_dir: str
    filename: str

    @classmethod
    def parse(cls, wire: str) -> BackupRef:
        """Parse a `device_dir/filename` reference from the websocket wire.

        PARAMETERS:
            wire (str): Candidate reference, e.g. the `filename` field
                returned by `list_backups`.

        RETURNS:
            BackupRef: The parsed, validated reference.

        RAISES:
            ValueError: If `wire` is not exactly two safe path segments.
        """
        parts = wire.split("/")
        if len(parts) != 2 or not all(_is_safe_segment(p) for p in parts):
            raise ValueError(f"Invalid backup reference: {wire!r}")
        return cls(device_dir=parts[0], filename=parts[1])

    @classmethod
    def for_capture(cls, device_dir: str, name: str) -> BackupRef:
        """Build the ref a capture job will write, from a validated name.

        PARAMETERS:
            device_dir (str): Sanitized device directory (or `"gold"`).
            name (str): Validated backup name (no `.tar.gz` suffix yet).

        RETURNS:
            BackupRef: Reference with `filename` set to `{name}.tar.gz`.
        """
        return cls(device_dir=device_dir, filename=f"{name}.tar.gz")

    def wire(self) -> str:
        """RETURNS: str: The `device_dir/filename` form sent to the frontend."""
        return f"{self.device_dir}/{self.filename}"

    def smb_remote(self, backup_dir: str) -> str:
        """RETURNS: str: SMB-relative path under the configured backup dir."""
        return f"{backup_dir}/{self.device_dir}/{self.filename}"

    def smb_meta_remote(self, backup_dir: str) -> str:
        """RETURNS: str: SMB-relative path of this backup's `.meta.json`."""
        meta_name = self.filename[: -len(".tar.gz")] if self.filename.endswith(".tar.gz") else self.filename
        return f"{backup_dir}/{self.device_dir}/{meta_name}.meta.json"

    def local_path(self, staging: Path) -> Path:
        """RETURNS: Path: Where this archive lands inside a staging dir.

        Only the basename is used locally — `device_dir` exists purely as
        an SMB-side namespacing convention and must never be joined into a
        local filesystem path (doing so previously produced an unreachable
        nested path that made "deploy a specific backup" fail outright).
        """
        return staging / os.path.basename(self.filename)

    @property
    def archive_root(self) -> str:
        """RETURNS: str: The top-level directory name inside the archive itself.

        Capture always tars the on-device Kodi directory as `.kodi/`
        regardless of what the archive file is named — this is the fixed
        constant deploy must extract to, not something derived from the
        backup's filename.
        """
        return ARCHIVE_ROOT

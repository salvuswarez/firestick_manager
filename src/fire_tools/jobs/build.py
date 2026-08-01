"""Build job: turn a raw capture into a ready-to-deploy Kodi profile.

Everything that shapes *what* gets deployed happens here — addon pruning,
settings overrides, home-screen hub layout, view-type fixes — so that deploy
is nothing but a transfer. Previously all of this ran per-device inside
deploy, which meant identical work repeated for every stick and a deploy that
could fail for reasons having nothing to do with the device.

The output is a flat archive (`addons/`, `userdata/`, `media/` at the tar
root) published under `builds/` on SMB.
"""

from __future__ import annotations

import logging
import tarfile
from datetime import datetime
from pathlib import Path

from .._addon_policy import prune_addons
from .._artifacts import BUILD_DEVICE_DIR, GOLD_DEVICE_DIR, BackupRef
from .._hub_layout import apply_hub_layout
from .._settings_overrides import apply_setting_overrides, remove_thumbnail_path_substitution
from .._smb import SmbClient
from .._view_types import apply_view_type_overrides
from ..models import BackupMeta, SmbConfig
from ..operations import OperationHandle

LOGGER = logging.getLogger(__name__)

PROFILE_FOLDERS = ("addons", "userdata", "media")


def run_build(
    handle: OperationHandle,
    ws: Path,
    *,
    source: str | None,
    smb: SmbClient,
    config: SmbConfig,
) -> str:
    """Build a deployable profile from a raw capture and publish it to SMB.

    **PARAMETERS:**
        `handle` (OperationHandle): Handle to log through and check cancellation.  <br>
        `ws` (Path): Per-operation staging directory.  <br>
        `source` (str | None): ``device_dir/filename`` of the raw capture to build from, or ``None`` for the most recent capture under ``gold/``.  <br>
        `smb` (SmbClient): Configured SMB client.  <br>
        `config` (SmbConfig): Resolved SMB backup directory.  <br>

    **RETURNS:**
        `str`: The SMB-relative path of the published build.  <br>

    **RAISES:**
        `RuntimeError`: If no source capture can be found, or it has no archive root.  <br>
    """
    ref = BackupRef.parse(source) if source else _latest_gold_capture(handle, smb, config)

    handle.log(f"Downloading source capture {ref.wire()}...")
    local_tar = ref.local_path(ws)
    smb.download_file(ref.smb_remote(config.smb_backup_dir), str(local_tar))

    handle.log("Extracting...")
    with tarfile.open(local_tar, "r:gz") as tar:
        tar.extractall(ws, filter="data")
    profile = ws / ref.archive_root
    if not profile.is_dir():
        raise RuntimeError(f"Capture {ref.wire()} has no {ref.archive_root}/ root")

    handle.check_cancelled()
    handle.log("Pruning addons to the gold whitelist...")
    removed = prune_addons(profile / "addons")
    if removed:
        handle.log(f"Removed {len(removed)} non-whitelisted addon(s): {', '.join(removed)}")

    handle.check_cancelled()
    handle.log("Applying known-good settings overrides...")
    for change in apply_setting_overrides(profile / "userdata"):
        handle.log(f"  {change}")
    if remove_thumbnail_path_substitution(profile / "userdata"):
        handle.log("  advancedsettings.xml: removed network thumbnail path substitution")

    handle.check_cancelled()
    handle.log("Regenerating home-screen hub layout...")
    for change in apply_hub_layout(profile / "userdata"):
        handle.log(f"  {change}")

    handle.check_cancelled()
    handle.log("Fixing view-type consistency (TV shows/seasons: library vs plugin)...")
    for change in apply_view_type_overrides(profile / "addons"):
        handle.log(f"  {change}")

    handle.check_cancelled()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    build_ref = BackupRef.for_capture(BUILD_DEVICE_DIR, f"build_{timestamp}")
    build_tar = build_ref.local_path(ws)

    handle.log(f"Packing {build_ref.filename}...")
    _pack_flat(profile, build_tar)

    smb_remote = build_ref.smb_remote(config.smb_backup_dir)
    handle.log(f"Uploading to SMB: {smb_remote}")
    smb.makedirs(f"{config.smb_backup_dir}/{BUILD_DEVICE_DIR}")
    size = smb.upload_file(str(build_tar), smb_remote)

    meta = _source_meta(smb, config, ref)
    meta.device_name = "build"
    meta.captured_at = datetime.now().isoformat()
    meta.size = size
    smb.write_text(build_ref.smb_meta_remote(config.smb_backup_dir), meta.model_dump_json(indent=2))

    handle.log(f"Build ready: {smb_remote}")
    return smb_remote


def _pack_flat(profile: Path, dest: Path) -> None:
    """Write `profile`'s Kodi folders to `dest` as a flat gzipped tar.

    Flat means `addons/...` rather than `.kodi/addons/...`, so the device can
    extract straight into its Kodi directory.
    """
    with tarfile.open(dest, "w:gz") as tar:
        for folder in PROFILE_FOLDERS:
            path = profile / folder
            if path.is_dir():
                tar.add(path, arcname=folder)


def _latest_gold_capture(handle: OperationHandle, smb: SmbClient, config: SmbConfig) -> BackupRef:
    handle.log("Finding latest gold capture...")
    candidates: list[str] = []
    try:
        for entry in smb.scandir(f"{config.smb_backup_dir}/{GOLD_DEVICE_DIR}"):
            if entry.name.endswith(".tar.gz"):
                candidates.append(entry.name)
    except Exception as exc:
        LOGGER.debug("SMB scandir failed for %s: %s", GOLD_DEVICE_DIR, exc)
    if not candidates:
        raise RuntimeError("No gold capture found — run a gold capture first")
    return BackupRef(device_dir=GOLD_DEVICE_DIR, filename=sorted(candidates)[-1])


def _source_meta(smb: SmbClient, config: SmbConfig, ref: BackupRef) -> BackupMeta:
    """Read the source capture's metadata, falling back to an empty record.

    Carried onto the build so `list_backups` can still report which Kodi and
    Arctic Fuse versions a build contains.

    **RETURNS:**
        `BackupMeta`: The source capture's metadata, or an empty record if no readable sidecar exists.  <br>
    """
    try:
        return BackupMeta.model_validate_json(smb.read_text(ref.smb_meta_remote(config.smb_backup_dir)))
    except Exception as exc:
        LOGGER.debug("No readable meta for source %s: %s", ref.wire(), exc)
        return BackupMeta()

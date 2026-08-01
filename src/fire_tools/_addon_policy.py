"""Addon allow-list applied to a backup's `addons/` folder before deploy.

Deploy previously pushed every addon in a captured backup unfiltered (see
the `architecture_job_pipeline` project memory) — this reintroduces the
curated allow-list an earlier core.py/glossary.py-based architecture had,
rebuilt 2026-07-30 from what's actually installed on the current gold
device rather than carrying forward the prior stale list.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Generic dependency/engine categories - safe to allow by prefix because
# they only provide libraries/services other addons depend on, never a
# standalone content source of their own.
REQUIRED_PREFIXES = (
    "script.module.",
    "service.",
    "metadata.",
    "resource.",
    "inputstream.",
    "repository.",
)

# Content/standalone addons specific to the Arctic Fuse 3 + Umbrella +
# TMDbHelper gold build (see reference_kodi_target.md and the
# kodi-gold-config skill's Arctic Fuse home-UI section). Update this list
# when the gold device's addon set intentionally changes.
WHITELIST_ADDONS = (
    "skin.arctic.fuse.3",
    "plugin.video.umbrella",
    "plugin.video.themoviedb.helper",
    "plugin.video.youtube",
    "plugin.program.autocompletion",
    "plugin.program.lazylinks",
    "plugin.program.thecrewiz",
    "pvr.iptvsimple",
    "script.embuary.helper",
    "script.embuary.info",
    "script.globalsearch",
    "script.skinvariables",
    "script.texturemaker",
)


def prune_addons(addons_dir: Path) -> list[str]:
    """Remove any addon folder not in the allow-list from an extracted backup.

    PARAMETERS:
        addons_dir (Path): The `addons/` folder inside an extracted backup,
            mutated in place. A no-op if it doesn't exist.

    RETURNS:
        list[str]: Names of addon folders that were removed.
    """
    if not addons_dir.is_dir():
        return []
    removed: list[str] = []
    for entry in sorted(addons_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in WHITELIST_ADDONS or entry.name.startswith(REQUIRED_PREFIXES):
            continue
        shutil.rmtree(entry)
        removed.append(entry.name)
    return removed

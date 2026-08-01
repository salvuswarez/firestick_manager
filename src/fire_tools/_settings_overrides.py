"""Known-good corrections applied to specific userdata settings files before
a deploy pushes them to a device.

Independent of whatever the capture source currently has — the gold device
(master bedroom) is the one device we can't afford to get wrong, so these
fixes are applied here, in the deploy pipeline, and tested against a
disposable device first rather than by hand-editing the gold source and
hoping the next capture is right.

Found 2026-07-30 debugging a Kodi crash after navigating to the Arctic Fuse
Genres home hub: `startup.enablehubpreloading` was populating every home
hub's widgets at once at startup (not just the visible one), TMDbHelper
allowed up to 10 concurrent background threads, and thumbnail caching was
redirected over network SMB instead of local storage — all compounding into
a low-memory kill (see gotcha_textures_db_stale_index memory).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

# (path relative to the extracted backup's userdata/, {setting id: new value})
SETTING_OVERRIDES: dict[str, dict[str, str]] = {
    "addon_data/skin.arctic.fuse.3/settings.xml": {
        # Was `true`: preloaded every HomeSwitcher tab's widgets at Kodi
        # startup instead of only the visible one.
        "startup.enablehubpreloading": "false",
        # Tab renames to match the layout in `_hub_layout.py`. Arctic Fuse
        # stores each of these under BOTH a lowercase and a PascalCase key
        # (an artifact of a skin-version migration) and reads whichever it
        # finds, so both spellings must be set or the tab keeps its old name.
        "homeswitcher.1102.name": "Series",
        "HomeSwitcher.1102.Name": "Series",
        "HomeSwitcher.1102.Shortcut.label": "Series",
        "homeswitcher.1104.name": "Browse",
        "HomeSwitcher.1104.Name": "Browse",
        "HomeSwitcher.1104.Shortcut.label": "Browse",
        # Hides the Addons tab (slot 1108) from the HomeSwitcher bar, leaving
        # Live TV (1107) as the last tab. Includes_Home.xml gates the tab's
        # visibility on `!String.IsEmpty(...)`, so an empty string is "off".
        "homeswitcher.1108.toggle": "",
        # script.skinvariables only recompiles HomeSwitcher JSON into the
        # skin's rendered includes when this hash changes. Without
        # invalidating it, new hub JSON lands but the compiled includes stay
        # stale even across a Kodi restart + cache clear.
        "script-skinvariables-generator-hash": "invalidated-by-deploy",
    },
    "addon_data/plugin.video.themoviedb.helper/settings.xml": {
        # Was `10`: allowed up to 10 concurrent background discover/image
        # threads at once. Lower cap staggers the load instead of bursting.
        "max_threads": "4",
    },
}


def apply_setting_overrides(userdata_dir: Path) -> list[str]:
    """Apply `SETTING_OVERRIDES` to the extracted `userdata/` folder.

    PARAMETERS:
        userdata_dir (Path): The `userdata/` folder inside an extracted
            backup, mutated in place. Missing files are skipped, not errors
            (an older/newer backup may not have every addon installed).

    RETURNS:
        list[str]: Human-readable description of each value actually changed.
    """
    changes: list[str] = []
    for rel_path, overrides in SETTING_OVERRIDES.items():
        path = userdata_dir / rel_path
        if not path.is_file():
            continue
        tree = ET.parse(path)
        root = tree.getroot()
        changed = False
        for setting_id, new_value in overrides.items():
            elem = root.find(f"./setting[@id='{setting_id}']")
            if elem is None or elem.text == new_value:
                continue
            changes.append(f"{rel_path}: {setting_id} = {new_value} (was {elem.text!r})")
            elem.text = new_value
            changed = True
        if changed:
            tree.write(path, encoding="UTF-8", xml_declaration=False)
    return changes


def remove_thumbnail_path_substitution(userdata_dir: Path) -> bool:
    """Remove a `<pathsubstitution>` entry that redirects thumbnail caching
    over network SMB, restoring Kodi's default local thumbnail cache.

    PARAMETERS:
        userdata_dir (Path): The `userdata/` folder inside an extracted
            backup, mutated in place.

    RETURNS:
        bool: True if `advancedsettings.xml` was changed.
    """
    path = userdata_dir / "advancedsettings.xml"
    if not path.is_file():
        return False
    tree = ET.parse(path)
    root = tree.getroot()
    changed = False
    for pathsub in root.findall("pathsubstitution"):
        for sub in list(pathsub.findall("substitute")):
            frm = sub.find("from")
            if frm is not None and frm.text and "thumbnails" in frm.text.lower():
                pathsub.remove(sub)
                changed = True
        if len(pathsub) == 0:
            root.remove(pathsub)
    if changed:
        tree.write(path, encoding="UTF-8", xml_declaration=False)
    return changed

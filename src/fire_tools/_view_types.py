"""Corrections to Arctic Fuse 3's compiled view-type routing.

`script-skinviewtypes-includes.xml` maps a container's content type to a
numbered view id. Shipped defaults render TV shows and seasons differently
depending on whether the content came from the library or a plugin; movies
don't. These three expressions make both unconditional:

- `Exp_View_505` (Card Row) — movies OR tvshows, always.
- `Exp_View_521` (Landscape Combined) — drops its seasons clause.
- `Exp_View_524` (Board Combined) — drops both tvshows clauses; seasons
  becomes unconditional.

Wall views (510-514) stay disabled — low-memory devices, see
`_settings_overrides.py`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

_SKIN_VIEWTYPES_REL = "skin.arctic.fuse.3/1080i/script-skinviewtypes-includes.xml"

VIEW_EXPRESSION_OVERRIDES: dict[str, str] = {
    "Exp_View_505": (
        "[[Container.Content(movies) + [[String.IsEmpty(Container.PluginName) | "
        "String.IsEqual(Container.PluginName,plugin.video.themoviedb.helper)] | "
        "[!String.IsEmpty(Container.PluginName)]]] | [Container.Content(tvshows)]]"
    ),
    "Exp_View_521": ("[Container.Content() + String.IsEqual(Container.Property(param.info),watch_providers) + " "[!String.IsEmpty(Container.PluginName)]]"),
    "Exp_View_524": (
        "[[Container.Content(sets) + [[String.IsEmpty(Container.PluginName)] | [!String.IsEmpty(Container.PluginName)]]] | "
        "[Container.Content(seasons)] | "
        "[Container.Content(videoversions) + [[String.IsEmpty(Container.PluginName)] | [!String.IsEmpty(Container.PluginName)]]] | "
        "[!Window.IsVisible(MyMusicNav.xml) + Container.Content(genres) + [[String.IsEmpty(Container.PluginName)] | [!String.IsEmpty(Container.PluginName)]]] | "
        "[Container.Content(studios) + [[String.IsEmpty(Container.PluginName)] | [!String.IsEmpty(Container.PluginName)]]] | "
        "[Container.Content(playlists) + [String.IsEmpty(Container.PluginName)]] | "
        "[Container.Content() + String.IsEqual(Container.Property(param.info),watch_providers) + [String.IsEmpty(Container.PluginName)]]]"
    ),
}


def apply_view_type_overrides(addons_dir: Path) -> list[str]:
    """Patch the drifted view-type `<expression>` rules so TV shows and
    seasons stop rendering differently depending on whether the content
    came from the local library or a plugin.

    PARAMETERS:
        addons_dir (Path): The `addons/` folder inside an extracted backup.
            Missing file is skipped, not an error (an older/newer skin
            build may not ship it, or the skin may not be installed).

    RETURNS:
        list[str]: Human-readable description of each expression changed.
    """
    path = addons_dir / _SKIN_VIEWTYPES_REL
    if not path.is_file():
        return []
    tree = ET.parse(path)
    root = tree.getroot()
    changes: list[str] = []
    for name, new_value in VIEW_EXPRESSION_OVERRIDES.items():
        elem = root.find(f"./expression[@name='{name}']")
        if elem is None or elem.text == new_value:
            continue
        changes.append(f"{name}: updated")
        elem.text = new_value
    if changes:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return changes

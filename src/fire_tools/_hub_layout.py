"""Arctic Fuse home-screen layout, generated at deploy time.

Arctic Fuse 3 drives its home screen from three separate config layers that
can (and did) drift out of sync:

1. **HomeSwitcher slots** — the top-level tabs, configured as skin settings
   (`skin.arctic.fuse.3/settings.xml`). Handled in `_settings_overrides.py`.
2. **skinvariables submenu/widget JSON** — the sub-tabs and the widget rows
   actually rendered for each slot, under
   `userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/`.
3. **TMDbHelper node JSON** — what a hub shows when you *navigate into* it,
   under `userdata/addon_data/plugin.video.themoviedb.helper/nodes/`.

Generating (2) and (3) from the one `HUBS` definition below is the point of
this module: previously the captured gold config had e.g. Movies listing
seven rows as a node but only four as widgets, so browsing into a hub showed
different content than its home rows.

**Why this also matters for stability:** slot 1104 ("Genres") was a flat
wall of ten live TMDb queries with no submenu and no local content, and
reproducibly preceded an OOM kill on a 1.7GB stick (see the
`gotcha_textures_db_stale_index` memory). It is rebuilt as "Browse": a pure
index that calls the same row-generator functions Movies/Series use for
their own submenus, so it can never drift into a second definition of the
same content.

Slots deliberately NOT touched by this module: 1103 (hand-curated), 1107
(Live TV). 1108 (Addons) is disabled outright in `_settings_overrides.py`,
so Live TV is the last visible tab.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_NODES_REL = "addon_data/plugin.video.themoviedb.helper/nodes"
_SKINVARS_REL = "addon_data/script.skinvariables/nodes/skin.arctic.fuse.3"

_TMDB = "plugin://plugin.video.themoviedb.helper/"
_ICON_TMDB = "special://home/addons/plugin.video.themoviedb.helper/resources/icons/themoviedb"
_ICON_WHITE = "special://home/addons/plugin.video.themoviedb.helper/resources/icons/white"
_ICON_SKIN = "special://skin/extras/icons"

# Slots this module owns. Anything else on the home screen is left alone.
MANAGED_SLOTS = ("home", "1101", "1102", "1104")


def _discover(tmdb_type: str, /, **params: Any) -> str:
    """RETURNS: str: A TMDbHelper `info=discover` plugin path.

    PARAMETERS:
        tmdb_type (str): Either `movie` or `tv`.
        **params (Any): Extra discover params (`with_genres`, `sort_by`, …).
            Underscores are NOT translated — TMDb's own param names contain
            dots (`vote_count.gte`), so pass those via `_p()` instead.
    """
    parts = [f"info=discover", "with_id=True", f"tmdb_type={tmdb_type}"]
    parts += [f"{k}={v}" for k, v in params.items()]
    return f"{_TMDB}?{'&'.join(parts)}&widget=True"


def _p(base: str, **params: Any) -> str:
    """RETURNS: str: `base` with extra dotted-name params appended."""
    extra = "&".join(f"{k.replace('__', '.')}={v}" for k, v in params.items())
    return f"{base}&{extra}" if extra else base


# Genre/network/company ids are TMDb's own. `%7C` is a URL-encoded pipe (OR).
_TV = {"comedy": 35, "drama": 18, "scifi": 10765, "animation": 16, "crime": 80, "docs": 99, "mystery": 9648, "reality": 10764}
_MOV = {
    "action": 28,
    "adventure": 12,
    "comedy": 35,
    "scifi": 878,
    "horror": 27,
    "family": 10751,
    "thriller": 53,
    "drama": 18,
    "crime": 80,
    "mystery": 9648,
    "docs": 99,
}
_NET = {"netflix": 213, "hbo": "49%7C3186", "apple": 2552, "disney": 2739, "paramount": 4330, "hulu": 453}
# Reused as-is from the gold device's captured config.
_INTL_NET = {"abs_cbn": 156, "gma": 210, "viu": 1510}
_STUDIO = {"marvel": 420, "pixar": 3, "a24": 41077, "ghibli": 10342}

# Kodi library smartlists — local, instant, no network round-trip. Every hub
# leads with these so something renders before any TMDb call resolves.
_LIB_TV_PROGRESS = "library://video/tvshows/inprogressshows.xml/"
_LIB_TV_RECENT = "library://video/tvshows/recentlyaddedepisodes.xml/"
_LIB_MOV_PROGRESS = "library://video/movies/inprogressmovies.xml/"
_LIB_MOV_RECENT = "library://video/movies/recentlyaddedmovies.xml/"


def _row(label: str, path: str, icon: str) -> dict[str, str]:
    return {"label": label, "path": path, "icon": icon, "target": "videos"}


def _tv_genre_rows() -> list[dict[str, str]]:
    return [
        _row("Drama", _p(_discover("tv", with_genres=_TV["drama"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/tv.png"),
        _row("Comedy", _p(_discover("tv", with_genres=_TV["comedy"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/tv.png"),
        _row("Sci-Fi & Fantasy", _p(_discover("tv", with_genres=_TV["scifi"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/tv.png"),
        _row("Animation", _p(_discover("tv", with_genres=_TV["animation"], sort_by="popularity.desc"), vote_count__gte=50), f"{_ICON_TMDB}/tv.png"),
        _row("Reality", _p(_discover("tv", with_genres=_TV["reality"], sort_by="popularity.desc"), vote_count__gte=20), f"{_ICON_TMDB}/genre.png"),
        _row("Documentary", _p(_discover("tv", with_genres=_TV["docs"], sort_by="popularity.desc"), vote_count__gte=20), f"{_ICON_TMDB}/genre.png"),
    ]


def _movie_genre_rows() -> list[dict[str, str]]:
    return [
        _row(
            "Action & Adventure",
            _p(_discover("movie", with_genres=f"{_MOV['action']}%7C{_MOV['adventure']}", sort_by="popularity.desc"), vote_count__gte=500),
            f"{_ICON_TMDB}/movies.png",
        ),
        _row("Comedy", _p(_discover("movie", with_genres=_MOV["comedy"], sort_by="popularity.desc"), vote_count__gte=300), f"{_ICON_TMDB}/movies.png"),
        _row("Sci-Fi", _p(_discover("movie", with_genres=_MOV["scifi"], sort_by="popularity.desc"), vote_count__gte=200), f"{_ICON_TMDB}/movies.png"),
        _row("Thriller", _p(_discover("movie", with_genres=_MOV["thriller"], sort_by="popularity.desc"), vote_count__gte=200), f"{_ICON_TMDB}/movies.png"),
        _row("Horror", _p(_discover("movie", with_genres=_MOV["horror"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/movies.png"),
        _row("Family", _p(_discover("movie", with_genres=_MOV["family"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/movies.png"),
        _row("Drama", _p(_discover("movie", with_genres=_MOV["drama"], sort_by="popularity.desc"), vote_count__gte=300), f"{_ICON_TMDB}/movies.png"),
    ]


def _streaming_rows(tmdb_type: str = "tv") -> list[dict[str, str]]:
    # NOTE: the captured config had this row's icon set to a repository .zip
    # URL (`repository.thecrew-0.3.8.zip`) — a paste error that can never
    # resolve as an image. Regenerated with real icons here.
    return [
        _row("Netflix", _discover(tmdb_type, with_networks=_NET["netflix"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("HBO / Max", _discover(tmdb_type, with_networks=_NET["hbo"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("Apple TV+", _discover(tmdb_type, with_networks=_NET["apple"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("Disney+", _discover(tmdb_type, with_networks=_NET["disney"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("Paramount+", _discover(tmdb_type, with_networks=_NET["paramount"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("Hulu", _discover(tmdb_type, with_networks=_NET["hulu"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
    ]


def _decade_rows() -> list[dict[str, str]]:
    out = []
    for label, lo, hi in [
        ("2020s", "2020-01-01", "2029-12-31"),
        ("2010s", "2010-01-01", "2019-12-31"),
        ("2000s", "2000-01-01", "2009-12-31"),
        ("90s", "1990-01-01", "1999-12-31"),
        ("Classics (pre-1990)", "1900-01-01", "1989-12-31"),
    ]:
        path = _p(_discover("movie", sort_by="popularity.desc"), vote_count__gte=200, primary_release_date__gte=lo, primary_release_date__lte=hi)
        out.append(_row(label, path, f"{_ICON_TMDB}/movies.png"))
    return out


def _tv_decade_rows() -> list[dict[str, str]]:
    out = []
    for label, lo, hi in [
        ("2020s", "2020-01-01", "2029-12-31"),
        ("2010s", "2010-01-01", "2019-12-31"),
        ("2000s", "2000-01-01", "2009-12-31"),
        ("Classic TV (pre-2000)", "1900-01-01", "1999-12-31"),
    ]:
        path = _p(_discover("tv", sort_by="popularity.desc"), vote_count__gte=100, first_air_date__gte=lo, first_air_date__lte=hi)
        out.append(_row(label, path, f"{_ICON_TMDB}/tv.png"))
    return out


def _crime_docs_mystery_row(tmdb_type: str) -> dict[str, str]:
    genres = f"{_MOV['crime']}%7C{_MOV['mystery']}%7C{_MOV['docs']}"
    icon = f"{_ICON_TMDB}/movies.png" if tmdb_type == "movie" else f"{_ICON_TMDB}/tv.png"
    return _row("Crime, Docs & Mystery", _p(_discover(tmdb_type, with_genres=genres, sort_by="popularity.desc"), vote_count__gte=100), icon)


def _movie_collection_rows() -> list[dict[str, str]]:
    return [
        _row("Top Rated (90%+)", _p(_discover("movie", sort_by="popularity.desc"), vote_average__gte=8.0, vote_count__gte=2000), f"{_ICON_TMDB}/popular.png"),
        _row(
            "Crime & Thriller",
            _p(_discover("movie", with_genres=f"{_MOV['crime']}%7C{_MOV['thriller']}", sort_by="popularity.desc"), vote_count__gte=100),
            f"{_ICON_TMDB}/movies.png",
        ),
        _row(
            "New This Month",
            _p(
                _discover("movie", sort_by="primary_release_date.desc", with_original_language="en"),
                vote_count__gte=10,
                primary_release_date__lte="T-0",
                primary_release_date__gte="T-30",
            ),
            f"{_ICON_TMDB}/intheatres.png",
        ),
        _row("Hidden Gems", _p(_discover("movie", sort_by="vote_average.desc"), vote_count__gte=50, vote_count__lte=400), f"{_ICON_TMDB}/movies.png"),
    ]


def _studio_rows() -> list[dict[str, str]]:
    return [
        _row("Marvel", _discover("movie", with_companies=_STUDIO["marvel"], sort_by="primary_release_date.desc"), f"{_ICON_TMDB}/movies.png"),
        _row("Pixar", _discover("movie", with_companies=_STUDIO["pixar"], sort_by="primary_release_date.desc"), f"{_ICON_TMDB}/movies.png"),
        _row("A24", _discover("movie", with_companies=_STUDIO["a24"], sort_by="primary_release_date.desc"), f"{_ICON_TMDB}/movies.png"),
        _row("Studio Ghibli", _discover("movie", with_companies=_STUDIO["ghibli"], sort_by="primary_release_date.desc"), f"{_ICON_TMDB}/movies.png"),
    ]


def _international_rows() -> list[dict[str, str]]:
    # K-Dramas/Anime use origin-country + genre — TMDb has no network id for
    # either as a category.
    return [
        _row("ABS-CBN", _discover("tv", with_networks=_INTL_NET["abs_cbn"], sort_by="first_air_date.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("GMA", _discover("tv", with_networks=_INTL_NET["gma"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("Viu", _discover("tv", with_networks=_INTL_NET["viu"], sort_by="popularity.desc"), f"{_ICON_TMDB}/discover.png"),
        _row("K-Dramas", _p(_discover("tv", sort_by="popularity.desc"), with_origin_country="KR", vote_count__gte=50), f"{_ICON_TMDB}/tv.png"),
        _row(
            "Anime",
            _p(_discover("tv", with_genres=_TV["animation"], sort_by="popularity.desc"), with_origin_country="JP", vote_count__gte=50),
            f"{_ICON_TMDB}/tv.png",
        ),
    ]


def _tv_critically_acclaimed_rows() -> list[dict[str, str]]:
    return [
        _row("Top Rated (90%+)", _p(_discover("tv", sort_by="popularity.desc"), vote_average__gte=8.0, vote_count__gte=500), f"{_ICON_TMDB}/popular.png"),
        _row("Hidden Gems", _p(_discover("tv", sort_by="vote_average.desc"), vote_count__gte=20, vote_count__lte=200), f"{_ICON_TMDB}/tv.png"),
    ]


# --- The single source of truth for every managed hub ------------------------
#
# `widgets` render as rows on the home screen for that tab; `submenu` renders
# as sub-tabs, each holding its own rows. Library rows come first everywhere so
# the screen paints from local data before any network call resolves.
HUBS: dict[str, dict[str, Any]] = {
    "home": {
        "node": "home_hub.json",
        "node_name": "HOME",
        "widgets": [
            _row("Continue Watching", _LIB_TV_PROGRESS, f"{_ICON_WHITE}/recent.png"),
            _row("Recently Added", _LIB_MOV_RECENT, f"{_ICON_WHITE}/calendar.png"),
            _row(
                "New Releases This Week",
                _p(
                    _discover("movie", sort_by="primary_release_date.desc", with_original_language="en"),
                    vote_count__gte=10,
                    primary_release_date__lte="T-0",
                    primary_release_date__gte="T-7",
                ),
                f"{_ICON_TMDB}/intheatres.png",
            ),
            _row("Trending Now", _discover("tv", sort_by="popularity.desc"), f"{_ICON_TMDB}/trending.png"),
            # Same genre math as Series > Crime, Docs & Mystery, surfaced on
            # home. The hand-curated 1103 hub is never touched.
            _row(
                "Picked for Maddy",
                _p(_discover("tv", with_genres=f"{_TV['crime']}%7C{_TV['mystery']}", sort_by="popularity.desc"), vote_count__gte=50),
                f"{_ICON_TMDB}/discover.png",
            ),
        ],
        "submenu": [],
    },
    "1101": {
        "node": "movies_hub_main.json",
        "node_name": "MOVIES",
        "widgets": [
            _row("Continue Watching", _LIB_MOV_PROGRESS, f"{_ICON_WHITE}/recent.png"),
            _row("Recently Added", _LIB_MOV_RECENT, f"{_ICON_WHITE}/calendar.png"),
            _row(
                "New Releases",
                _p(_discover("movie", sort_by="primary_release_date.desc", with_original_language="en"), vote_count__gte=25, primary_release_date__lte="T-0"),
                f"{_ICON_TMDB}/intheatres.png",
            ),
            _row("Comedy", _p(_discover("movie", with_genres=_MOV["comedy"], sort_by="popularity.desc"), vote_count__gte=300), f"{_ICON_TMDB}/movies.png"),
            _row("Sci-Fi", _p(_discover("movie", with_genres=_MOV["scifi"], sort_by="popularity.desc"), vote_count__gte=200), f"{_ICON_TMDB}/movies.png"),
            _crime_docs_mystery_row("movie"),
        ],
        "submenu": [
            ("Genres", f"{_ICON_SKIN}/genre.png", _movie_genre_rows()),
            ("Collections", f"{_ICON_SKIN}/genre.png", _movie_collection_rows()),
            ("By Decade", f"{_ICON_SKIN}/calendar.png", _decade_rows()),
            ("By Studio", f"{_ICON_SKIN}/genre.png", _studio_rows()),
        ],
    },
    "1102": {
        "node": "tv_hub_main.json",
        "node_name": "SERIES",
        "widgets": [
            _row("Continue Watching", _LIB_TV_PROGRESS, f"{_ICON_WHITE}/recent.png"),
            _row("Recently Added Episodes", _LIB_TV_RECENT, f"{_ICON_WHITE}/calendar.png"),
            _row(
                "New Premieres",
                _p(
                    _discover("tv", sort_by="first_air_date.desc", with_original_language="en"),
                    vote_count__gte=5,
                    first_air_date__lte="T-0",
                    first_air_date__gte="T-90",
                ),
                f"{_ICON_TMDB}/trending.png",
            ),
            _row("Drama", _p(_discover("tv", with_genres=_TV["drama"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/tv.png"),
            _crime_docs_mystery_row("tv"),
            _row("Sci-Fi", _p(_discover("tv", with_genres=_TV["scifi"], sort_by="popularity.desc"), vote_count__gte=100), f"{_ICON_TMDB}/tv.png"),
        ],
        "submenu": [
            ("Genres", f"{_ICON_SKIN}/genre.png", _tv_genre_rows()),
            ("By Network", f"{_ICON_SKIN}/rocket.png", _streaming_rows("tv")),
            ("International", f"{_ICON_SKIN}/genre.png", _international_rows()),
            ("By Decade", f"{_ICON_SKIN}/calendar.png", _tv_decade_rows()),
            ("Critically Acclaimed", f"{_ICON_SKIN}/genre.png", _tv_critically_acclaimed_rows()),
        ],
    },
    # A pure index over Movies'/Series' own submenus — every group below
    # calls the same row-generators those tabs use, so it can't drift.
    "1104": {
        "node": "genres_hub.json",
        "node_name": "BROWSE",
        # Deliberately light: this hub's job is the submenu, not widgets.
        # OOM history here means no wide fan-out of live rows.
        "widgets": [
            _row("Popular Movies", _p(_discover("movie", sort_by="popularity.desc"), vote_count__gte=300), f"{_ICON_TMDB}/popular.png"),
            _row(
                "New This Week",
                _p(_discover("tv", sort_by="first_air_date.desc"), vote_count__gte=5, first_air_date__lte="T-0", first_air_date__gte="T-7"),
                f"{_ICON_TMDB}/trending.png",
            ),
        ],
        "submenu": [
            ("Movie Genres", f"{_ICON_SKIN}/genre.png", _movie_genre_rows()),
            ("TV Genres", f"{_ICON_SKIN}/genre.png", _tv_genre_rows()),
            ("By Network", f"{_ICON_SKIN}/rocket.png", _streaming_rows("tv")),
            ("International", f"{_ICON_SKIN}/genre.png", _international_rows()),
        ],
    },
}


def _guid(*parts: str) -> str:
    """RETURNS: str: A stable `guid-xxxxxxxx` derived from `parts`.

    Deterministic rather than random so regenerating an unchanged hub
    produces a byte-identical file — which keeps the build step's
    hash comparison from re-pushing it on every deploy.
    """
    return "guid-" + hashlib.md5("|".join(parts).encode()).hexdigest()[:8]


def _blank_slot() -> dict[str, Any]:
    """RETURNS: dict: The empty trailing entry Arctic Fuse's own editor keeps.

    Every submenu written by the skin ends with one of these. It is a UI
    affordance ("add item"), not stray data — reproduced so a generated file
    matches what the skin would have written itself.
    """
    return {"label": "", "icon": "", "path": "", "target": "", "submenu": [], "widgets": [], "guid": _guid("blank")}


def _with_guids(rows: list[dict[str, str]], scope: str) -> list[dict[str, Any]]:
    return [dict(r, guid=_guid(scope, r["label"])) for r in rows]


def apply_hub_layout(userdata_dir: Path) -> list[str]:
    """Regenerate widget/submenu/node config for the managed hubs.

    PARAMETERS:
        userdata_dir (Path): The `userdata/` folder inside an extracted
            backup, mutated in place. Missing parent directories are
            created; unmanaged slots (1103 Crime, 1107 Live TV, 1108) are
            never read or written.

    RETURNS:
        list[str]: One human-readable line per file written.
    """
    skinvars = userdata_dir / _SKINVARS_REL
    nodes = userdata_dir / _NODES_REL
    skinvars.mkdir(parents=True, exist_ok=True)
    nodes.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for slot, spec in HUBS.items():
        widgets = _with_guids(spec["widgets"], slot)
        _write_json(skinvars / f"skinvariables-shortcut-{slot}widgets.json", widgets)
        written.append(f"{slot}: {len(widgets)} widget row(s)")

        submenu_spec = spec.get("submenu") or []
        if submenu_spec:
            submenu: list[dict[str, Any]] = []
            for label, icon, rows in submenu_spec:
                submenu.append(
                    {
                        "label": label,
                        "path": "Custom_Submenu",
                        "icon": icon,
                        "target": "",
                        "guid": _guid(slot, "sub", label),
                        "submenu": _with_guids(rows, f"{slot}:{label}"),
                    }
                )
            submenu.append(_blank_slot())
            _write_json(skinvars / f"skinvariables-shortcut-{slot}submenu.json", submenu)
            written.append(f"{slot}: {len(submenu) - 1} sub-tab(s)")

        # Keep the TMDbHelper node in step with the widgets so navigating
        # into a hub shows the same content its home rows advertise.
        node = {
            "name": spec["node_name"],
            "icon": f"{_ICON_TMDB}/discover.png",
            "list": [{"name": r["label"], "icon": r["icon"], "path": r["path"], "widget": "True"} for r in spec["widgets"]]
            + [{"name": lbl, "icon": ic, "path": rows[0]["path"], "widget": "True"} for lbl, ic, rows in submenu_spec if rows],
        }
        _write_json(nodes / spec["node"], node)

    return written


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")

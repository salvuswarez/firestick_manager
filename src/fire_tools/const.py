"""Shared constants: ADB paths, cleanup lists, and SMB defaults."""
from __future__ import annotations

# ADB
ADB_PORT = 5555
REMOTE_KODI_PATH = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
ARCHIVE_ROOT = ".kodi"

KODI_MIRROR_BASE_URL = "https://mirrors.kodi.tv/releases/android/arm/"

# SMB (router-USB / NAS) defaults — override via .env (CLI) or the HA config
# entry. NOTE: the CLI's historical default backup dir ("backups") and the
# HA integration's historical default ("kodi-wan/ha_storage/backups") are
# NOT the same path. Verify which one your actual stored config uses before
# assuming they share a backup tree on the share.
DEFAULT_SMB_HOST = "192.168.50.1"
DEFAULT_SMB_SHARE = "Kodi"
DEFAULT_SMB_BACKUP_DIR = "backups"
SMB_STATE_DIR = "fire_tools_state"

# Cache/temp paths cleaned before a backup is archived. Kept distinct from
# MAINTENANCE_PRUNE_PATHS because capture and maintain clean overlapping but
# not identical sets.
PRE_CAPTURE_PRUNE_PATHS = (
    "userdata/Thumbnails",
    "userdata/addon_data/plugin.video.themoviedb.helper/crop_v2",
    "userdata/addon_data/plugin.video.themoviedb.helper/blur_v3",
    "userdata/addon_data/plugin.video.themoviedb.helper/database_07",
    "userdata/addon_data/plugin.video.themoviedb.helper/pickle",
    "userdata/addon_data/plugin.video.umbrella/icon_packs",
    "userdata/addon_data/plugin.video.umbrella/cache.db",
    "addons/temp",
    "temp",
    "log",
)

MAINTENANCE_PRUNE_PATHS = (
    "temp",
    "log",
    "userdata/Thumbnails",
    "userdata/addon_data/plugin.video.themoviedb.helper/cache",
    "userdata/addon_data/script.skin.helper.service/cache",
    "addons/packages",
)

# Amazon/Fire OS bloat packages disabled during maintenance.
BLOAT_PACKAGES = (
    "com.amazon.shoptv.client", "com.amazon.shoptv.firetv.client",
    "com.amazon.alexashopping", "com.amazon.client.metrics",
    "com.amazon.device.logmanager", "com.amazon.tv.fw.metrics",
    "com.amazon.kso.blackbird", "com.amazon.bueller.photos",
    "com.amazon.recess", "com.amazon.tahoe", "com.amazon.ags.app",
    "com.amazon.ods.kindleconnect", "com.amazon.logan",
    "com.amazon.device.software.ota",
    "com.amazon.kindle.otter.oobe.corp.ad",
    "com.amazon.firehomestarter", "com.amazon.venezia",
    "com.amazon.avod", "com.amazon.firebat", "com.amazon.tv.nimble",
)

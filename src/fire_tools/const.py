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

# Amazon/Fire OS bloat packages disabled during maintenance. Goal: the
# device should end up running essentially only Kodi + ExpressVPN +
# YouTube (see `plugin.program.thecrewiz`/kodi-gold-config skill for the
# Kodi-side equivalent, `_addon_policy.py`). Deliberately NOT touched:
# `org.xbmc.kodi`, `com.amazon.firetv.youtube`, `com.expressvpn.vpn` (the
# three apps meant to survive), core UI/input/connectivity (launcher,
# settings, systemui, ime, bluetooth, wifi), and anything Alexa-voice
# related (the physical remote's mic button depends on it — ask the user
# before disabling any `com.amazon.alexa*`/`com.amazon.ale`/`com.amazon.aca`
# package, since that's a functionality tradeoff, not pure bloat).
BLOAT_PACKAGES = (
    # Shopping / storefront
    "com.amazon.shoptv.client", "com.amazon.shoptv.firetv.client",
    "com.amazon.alexashopping", "com.amazon.venezia",
    # Telemetry / usage metrics / crash reporting
    "com.amazon.client.metrics", "com.amazon.device.logmanager",
    "com.amazon.tv.fw.metrics", "com.amazon.kso.blackbird",
    "com.amazon.minerva.client.api", "com.amazon.perfc",
    "com.amazon.perfcollection", "com.amazon.csm.htmlruntime",
    "com.amazon.wirelessmetrics.service", "com.amazon.device.crashmanager",
    "com.amazon.device.metrics", "com.amazon.dp.logger",
    "com.amazon.recess", "com.amazon.tahoe", "com.amazon.ags.app",
    "com.amazon.logan", "com.amazon.firebat",
    # Ad targeting / content recognition
    "com.amazon.tv.acr", "com.amazon.ftvads.deeplinking",
    "com.amazon.hybridadidservice", "com.amazon.d3",
    # Onboarding / tutorial / promotional nag screens
    "com.amazon.firehomestarter", "com.amazon.storm.lightning.tutorial",
    "com.amazon.tmm.tutorial", "com.amazon.tv.releasenotes",
    "com.amazon.systemnotices", "com.amazon.uxnotification",
    "com.amazon.tv.notificationcenter", "com.amazon.whisperjoin.middleware.np",
    # Prime Video specific (not used - Kodi/YouTube only)
    "com.amazon.awvflingreceiver", "com.amazon.stillwatching.activity",
    # Reading/photos/kindle ecosystem, misc unused apps
    "com.amazon.ods.kindleconnect", "com.amazon.bueller.photos",
    "com.amazon.minitv.android.app",
    # OTA update mechanism (deliberately disabled - see original list)
    "com.amazon.device.software.ota", "com.amazon.device.software.ota.override",
    "com.amazon.kindle.otter.oobe.corp.ad",
    "com.amazon.avod", "com.amazon.tv.nimble",
)

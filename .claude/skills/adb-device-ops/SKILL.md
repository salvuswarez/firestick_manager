---
name: adb-device-ops
description: ADB command patterns and Fire TV-specific quirks used across firestick_manager (connection, shell settings, package management, push/pull). Use when writing or debugging ADB commands against a Fire Stick.
---

# ADB Device Operations Reference

All device interaction in this repo goes through `adb`, always targeting `-s {ip}:5555` (Fire TV's fixed ADB-over-network port).

## Connection

```bash
adb connect <ip>:5555          # must run before any -s targeted command; idempotent, safe to repeat
adb -s <ip>:5555 shell <cmd>   # targeted shell command
adb disconnect <ip>:5555       # scanner.py disconnects after identifying a device; core.py does not
```

`Firestick.run_adb()` (`core.py`) wraps `subprocess.run(f"adb {target} {cmd}", shell=True, capture_output=True, text=True)` and returns stripped stdout — errors are captured but not raised; callers must check the returned string, not exceptions.

## Package Management (debloat)

```bash
adb -s <ip>:5555 shell pm disable-user --user 0 <package>   # reversible debloat (used)
adb -s <ip>:5555 shell pm enable <package>                   # restore (legacy root script only, not in core.py)
adb -s <ip>:5555 shell pm trim-caches 16G                    # global cache trim
adb -s <ip>:5555 shell pm clear com.amazon.bueller.photos    # specific app cache clear
```

`pm disable-user` is preferred over `pm uninstall` — it's reversible and doesn't risk bricking OTA/system behavior.

## System Tweaks (optimize / telemetry)

```bash
adb -s <ip>:5555 shell settings put global window_animation_scale 0.0
adb -s <ip>:5555 shell settings put global transition_animation_scale 0.0
adb -s <ip>:5555 shell settings put global animator_duration_scale 0.0
adb -s <ip>:5555 shell am trim-memory --all

adb -s <ip>:5555 shell settings put secure limit_ad_tracking 1
adb -s <ip>:5555 shell settings put global marketing_allowed 0
adb -s <ip>:5555 shell settings put global data_monitoring_enabled 0
```

## Discovery (Scanner)

```bash
ping -n 1 -w 150 <ip>     # Windows-style ping used by scanner.py (150ms timeout)
arp -a                     # local ARP cache, parsed for IP<->MAC mapping
adb -s <ip>:5555 shell settings get global device_name     # friendly name, may be null
adb -s <ip>:5555 shell getprop ro.product.model             # fallback if device_name is empty/null
```

## Push / Pull

```bash
adb -s <ip>:5555 pull /sdcard/Android/data/org.xbmc.kodi/files/.kodi "assets/.kodi_<timestamp>"
adb -s <ip>:5555 push "assets/.kodi_<timestamp>/addons" /sdcard/Android/data/org.xbmc.kodi/files/.kodi/
```

## Gotchas

- A device must have ADB debugging **enabled and already paired once** for `adb connect` to succeed silently — there's no pairing flow in this codebase.
- `subprocess.run(..., shell=True)` is used throughout — IP addresses are trusted input (from `devices.yml` or a CLI arg), not sanitized. Don't extend this to accept untrusted network input without adding validation.
- Fire OS 5+ locks down `pm disable-user` for some system packages from a non-root ADB shell (`SecurityException`, uid=2000) — if debloat silently no-ops on a package, that's likely why; there's no in-repo workaround (the more advanced sibling copy notes router-level DNS blocking as the fallback — see `.claude/memory/reference_fire_tools_forks.md`).

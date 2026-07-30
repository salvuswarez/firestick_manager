---
name: Kodi build target
description: APK source and skin/addon target this repo's gold-config pipeline is tuned for.
type: reference
---

APK source: `https://mirrors.kodi.tv/releases/android/arm/` (ARMv7/armeabi-v7a — the 32-bit build Fire Sticks need). Skin target: **Arctic Fuse 3** (`skin.arctic.fuse.3`) with the **Umbrella** addon family (`plugin.video.umbrella`, `repository.umbrella`) — `WHITELIST_ADDONS`/`REQUIRED_PREFIXES` in `glossary.py` are tuned specifically to this combination.

**Why:** Knowing the specific skin/build target explains why the whitelist looks the way it does (e.g. `script.skinvariables`/`script.texturemaker`/`script.globalsearch` are called out as "Critical for Arctic Fuse" in comments).

**How to apply:** If the user switches skins or addon repos, `WHITELIST_ADDONS` needs a corresponding update — don't assume it's skin-agnostic.

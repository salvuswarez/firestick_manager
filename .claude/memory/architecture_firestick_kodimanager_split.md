---
name: Firestick vs KodiManager split
description: core.py splits device-generic ops (Firestick) from Kodi-specific pipeline (KodiManager).
type: project
---

`src/fire_tools/core.py` has two classes: `Firestick` (device-generic — ADB connect, debloat, cache clean, system tweaks, telemetry blocking) and `KodiManager` (Kodi-specific — APK download, gold-image capture, config pruning, deploy). `KodiManager` takes a `Firestick` instance in its constructor and delegates raw ADB calls to it.

**Why:** Keeps "manage any Fire TV device" logic separate from "manage Kodi on a Fire TV device" logic, so device maintenance (`maintain` command) doesn't need to know anything about Kodi, and Kodi deployment doesn't need to reimplement ADB plumbing.

**How to apply:** New device-wide maintenance (e.g. a new debloat category) goes on `Firestick`. New Kodi-pipeline behavior (e.g. a new build format) goes on `KodiManager`, using `self.device.run_adb(...)` rather than shelling out directly.

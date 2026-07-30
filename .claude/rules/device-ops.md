---
paths: ["src/fire_tools/core.py", "src/fire_tools/scanner.py"]
---

# Device Operations Rules

When working in `core.py` or `scanner.py`:

1. **Always target `-s {ip}:5555`** — Fire TV's fixed ADB-over-network port. Never hardcode a different port or assume USB ADB.
2. **Call `connect()` before any targeted shell command** — it's idempotent and cheap; don't skip it to "optimize."
3. **Check command output, don't trust exit codes alone** — `run_adb()` returns stripped stdout via `capture_output=True`; several callers currently don't check it, but new code should.
4. **New device-wide maintenance goes on `Firestick`**, new Kodi-specific behavior goes on `KodiManager` — see `architecture_firestick_kodimanager_split` memory.
5. **Parallel scanning stays parallel** — don't collapse `Scanner`'s `ThreadPoolExecutor` sweeps into sequential loops; a full `/24` ping sweep is designed to take ~2 seconds, not 40.
6. **Destructive device ops need explicit user confirmation** — anything that force-stops Kodi, wipes the remote `.kodi` dir, or disables packages is pushing real state to a live device.

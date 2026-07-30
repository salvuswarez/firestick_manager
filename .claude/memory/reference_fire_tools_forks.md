---
name: three parallel fire-tools codebases
description: firestick_manager, ~/.config/opencode/tools/fire-tools, and ha-cyberpunk/scripts/fire-tools all implement overlapping Fire TV tooling that has diverged.
type: reference
---

Three codebases implement similar-but-diverged Fire TV Stick tooling:

1. **This repo** (`firestick_manager`) — standalone project, Poetry-then-uv, local `assets`/`archive` backup storage, no build-layering system.
2. **`~/.config/opencode/tools/fire-tools/`** (global, used by the OpenCode `fire-tools` skill) — the most feature-complete: SMB router-USB backup storage (`smb_put`/`smb_get`/`smb_list`), a layered `Build` class (`build`/`list-builds`, gold/clean base + extras like youtube/expressvpn), `list-backups`, `install-youtube`, `install-expressvpn`, a much larger curated `BLOAT_PACKAGES` list with categorized comments and a DNS-blocking fallback note for Fire OS 5+ `pm disable-user` restrictions.
3. **`ha-cyberpunk/scripts/fire-tools/`** — embedded in the Home Assistant config repo, plus a related `custom_components/firetools` HA integration (device scanner surfaced as an HA integration).

**Why this matters:** code, bug fixes, and BLOAT_PACKAGES/JUNK_PATHS updates made in one copy don't propagate to the others. The global opencode copy appears to be the actively-evolving one; this repo's copy looks like an earlier snapshot.

**How to apply:** Before assuming a behavior or fixing a bug, check which copy is actually in play. If the user wants feature parity (e.g., SMB backups, the `Build` system), treat the global copy as the reference implementation to port from rather than reinventing. Don't silently fork further — if a change seems like it should apply everywhere, say so explicitly rather than only fixing the one copy in front of you.

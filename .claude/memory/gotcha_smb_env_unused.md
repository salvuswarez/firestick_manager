---
name: SMB env vars are unused in this copy
description: .env defines SMB_HOST/SMB_SHARE/SMB_USER/SMB_PASS/SMB_BACKUP_DIR but nothing in src/fire_tools/ reads them.
type: project
---

This repo's `.env` has `SMB_HOST`, `SMB_SHARE`, `SMB_USER`, `SMB_PASS`, `SMB_BACKUP_DIR`, and `smbprotocol`/`pysmb` are real dependencies — but no code under `src/fire_tools/` (`cli.py`, `core.py`, `scanner.py`, `glossary.py`) references them. Backups here are purely local (`assets/`/`archive/`).

**Why:** The more feature-complete sibling copy at `~/.config/opencode/tools/fire-tools/` DOES use these exact env var names for router-USB SMB backup storage (`smb_put`/`smb_get`/`smb_list` in its `glossary.py`) — this repo's `.env` and dependencies look like a partial/planned port of that feature that was never finished. See `reference_fire_tools_forks.md`.

**How to apply:** Don't assume backups go to SMB/router-USB storage in this repo — they don't yet. If the user asks to add SMB backup, the sibling copy's implementation is a ready-made reference rather than something to design from scratch.

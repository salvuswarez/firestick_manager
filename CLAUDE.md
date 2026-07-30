# firestick_manager

CLI tool for managing a small fleet of Amazon Fire TV Stick devices: debloating, telemetry blocking, Kodi ("gold config") deployment, and network discovery. Entry point is `fire-tools` (`src/fire_tools/cli.py`), installed and run via `uv` (`uv run fire-tools ...`).

See `.claude/` for the deep reference: agents (`fleet-device-specialist`, `kodi-deploy-specialist`), skills (CLI reference, gold-config workflow, ADB ops, devices.yml schema), commands (`/fire-scan`, `/fire-capture`, `/fire-deploy`, `/fire-maintain`, `/fire-builds`), and project memory (architecture decisions, gotchas, cross-repo references).

## Quick facts

- Package manager: **uv** (migrated from Poetry — see `.claude/memory/architecture_uv_migration.md`)
- Domain module: `src/fire_tools/` — `cli.py` (Click commands), `core.py` (`Firestick` device ops + `KodiManager` Kodi pipeline), `scanner.py` (network discovery), `glossary.py` (config/constants, reads `resources/devices.yml`)
- No tests, no linter config yet — this is a small solo-maintainer utility, don't invent a heavier toolchain than it has
- `assets/` and `archive/` hold real captured Kodi backups (`.kodi_<timestamp>` snapshots) — data, not source; don't bulk-delete
- `kodi_deployment.py` at the repo root is legacy/superseded — see gotcha memory before touching it

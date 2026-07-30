# firestick_manager

CLI tool for managing a small fleet of Amazon Fire TV Stick devices: debloating, telemetry blocking, Kodi ("gold config") deployment, and network discovery. Entry point is `fire-tools` (`src/fire_tools/cli.py`), installed and run via `uv` (`uv run fire-tools ...`).

See `.claude/` for the deep reference: agents (`fleet-device-specialist`, `kodi-deploy-specialist`), skills (CLI reference, gold-config workflow, ADB ops, devices.yml schema), commands (`/fire-scan`, `/fire-capture`, `/fire-deploy`, `/fire-maintain`, `/fire-builds`), and project memory (architecture decisions, gotchas, cross-repo references).

## Setup

```bash
cp .env.example .env                              # fill in real SMB host/user/pass
cp resources/devices.yml.example resources/devices.yml   # or just run `uv run fire-tools scan`
uv sync
```

Both `.env` and `resources/devices.yml` are gitignored — real credentials and real device MAC/IP data never get committed. The `.example` files are the tracked reference for the expected shape; keep them in sync with `SmbConfig`/`Device` if those fields change.

## Quick facts

- Package manager: **uv** (migrated from Poetry — see `.claude/memory/architecture_uv_migration.md`)
- Also consumed as a library: `custom_components/firetools` in the sibling `ha-cyberpunk` repo installs this package via a `git+https://github.com/salvuswarez/firestick_manager.git@<tag>` requirement in its `manifest.json` and imports `fire_tools` directly (no code duplication between the CLI and the HA integration).
- Domain module: `src/fire_tools/` — pure-Python ADB (`_adb.py`, via `adb-shell`, no external `adb` binary needed), SMB (`_smb.py`, via `smbprotocol`), typed models (`models.py`, pydantic/dataclass), `device_store.py` (supports both `devices.yml` and `devices.json`), `operations.py` (background-op tracking with working cancellation), `jobs/` (capture/deploy/maintain/scan/fetch_base/display — the actual device logic, consumer-agnostic), `service.py` (`FleetService`, the orchestration facade), `cli.py` (Click commands, thin wrapper over the same job bodies)
- No tests, no linter config yet — this is a small solo-maintainer utility, don't invent a heavier toolchain than it has
- `assets/` and `archive/` hold real captured Kodi backups (`.kodi_<timestamp>` snapshots) — data, not source; don't bulk-delete
- `kodi_deployment.py` at the repo root is legacy/superseded — see gotcha memory before touching it

## Credentials & real device data — never commit

`.gitignore` excludes `.env` (SMB creds), `resources/devices.yml` (real MAC/IP inventory), and `resources/advancedsettings.xml` (real MySQL/SMB creds for Kodi). This list grew because a prior session used real device data as a documentation example in `.claude/skills/devices-config/SKILL.md`, which got committed and pushed before anyone caught it (later scrubbed via history rewrite).

**When writing or editing anything in `.claude/` (skills, agents, docs) or `resources/`**: use placeholder values only — `192.168.1.50`, `aa:bb:cc:dd:ee:ff`, fake names. Never copy a real IP/MAC/credential out of `.env` or `devices.yml` into a doc, example, or comment, even temporarily. Before committing, `git grep` for MAC-address and credential-looking patterns if you've touched anything under `.claude/` or `resources/`.

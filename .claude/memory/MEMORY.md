## Architecture Decisions

- [uv migration](architecture_uv_migration.md) — Poetry → uv, originals backed up as `.bak`
- [Firestick vs KodiManager split](architecture_firestick_kodimanager_split.md) — device-generic vs Kodi-specific classes
- [devices.yml source of truth](architecture_devices_yaml_source_of_truth.md) — scanner writes, glossary reads, `--batch` depends on it

## Gotchas

- [Legacy kodi_deployment.py](gotcha_legacy_kodi_deployment_script.md) — root script predates the package, not wired to the CLI
- [Capture never prunes, prep is opt-in](gotcha_capture_and_prep_semantics.md) — unbounded `assets/`/`archive/` growth, `--prep` is manual
- [SMB env vars unused here](gotcha_smb_env_unused.md) — `.env` has SMB_* but no code reads them in this copy

## Reference

- [Three fire-tools forks](reference_fire_tools_forks.md) — this repo, `~/.config/opencode/tools/fire-tools/`, and `ha-cyberpunk/scripts/fire-tools` have diverged
- [Kodi build target](reference_kodi_target.md) — ARMv7 mirror, Arctic Fuse 3 + Umbrella skin/addon target

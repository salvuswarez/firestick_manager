---
name: uv migration
description: This repo was migrated from Poetry to uv for package management.
type: project
---

`pyproject.toml` was converted from Poetry (`[tool.poetry]`, `poetry.lock`) to a plain PEP 621 `[project]` table with `hatchling` as the build backend, managed by `uv`. Original files preserved as `pyproject.toml.bak` / `poetry.lock.bak`.

**Why:** User standard is uv across all personal Python projects (matches `ha-cyberpunk`, which already used uv). Poetry was the original tool but never a deliberate choice for this repo specifically.

**How to apply:** Always use `uv run fire-tools ...` / `uv sync` / `uv add`, never `poetry run` or bare `python`. If you see a `poetry` command anywhere (docs, old notes, muscle memory), it's stale.

---
paths: ["src/fire_tools/cli.py"]
---

# CLI Rules

When working in `cli.py`:

1. **Every command needs `--batch` symmetry with single-IP mode** — `maintain`/`deploy` both accept either a positional `ip` or `--batch`; new fleet-wide commands should follow the same pattern via `get_device_configs()`.
2. **Raise `click.UsageError`, don't print-and-continue** — missing required args (IP or `--batch`) should fail loudly, matching the existing commands.
3. **Keep Click options declarative** — flags belong in the `@click.option` decorator, not parsed manually from `sys.argv`.
4. **New commands should be thin** — CLI functions here orchestrate; real logic belongs in `core.py`/`scanner.py`, not inline in the command body.

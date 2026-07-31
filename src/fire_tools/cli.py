"""Firestick maintenance and Kodi deployment CLI.

Thin wiring over the same job bodies (jobs/) and FleetService used by any
other consumer of this package (e.g. a Home Assistant integration) — every
command below is a synchronous, single-operation run of the identical code.
"""
from __future__ import annotations

import functools
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import click

from ._adb import _SHELL_TIMEOUT_S, _TRANSFER_TIMEOUT_S, AdbKeyStore, AdbShellRunner
from ._smb import SmbClient
from .const import DEFAULT_SMB_BACKUP_DIR, DEFAULT_SMB_HOST, DEFAULT_SMB_SHARE
from .device_store import DeviceStore
from .jobs import capture as _capture_job
from .jobs import deploy as _deploy_job
from .jobs import display as _display_job
from .jobs import fetch_base as _fetch_base_job
from .jobs import maintain as _maintain_job
from .jobs import scan as _scan_job
from .jobs._runner import run_job
from .models import OperationStatus, OperationType, SmbConfig
from .operations import NullOperationSink, OperationRegistry
from .service import FleetService

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOME_DIR = Path.home() / ".fire_tools"
_ADB_KEY_DIR = _HOME_DIR / "adb_keys"
_STAGING_ROOT = _HOME_DIR / "staging"
_DEVICES_YAML = Path(os.environ.get("FIRE_TOOLS_DEVICES", "resources/devices.yml"))


def _load_env() -> dict[str, str]:
    env_path = _REPO_ROOT / ".env"
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def _build_config() -> SmbConfig:
    env = _load_env()
    return SmbConfig.from_mapping({
        "smb_host": env.get("SMB_HOST", DEFAULT_SMB_HOST),
        "smb_share": env.get("SMB_SHARE", DEFAULT_SMB_SHARE),
        "smb_user": env.get("SMB_USER", ""),
        "smb_pass": env.get("SMB_PASS", ""),
        "smb_backup_dir": env.get("SMB_BACKUP_DIR", DEFAULT_SMB_BACKUP_DIR),
    })


def _adb_keys() -> AdbKeyStore:
    env = _load_env()
    return AdbKeyStore(
        _ADB_KEY_DIR,
        shell_timeout_s=float(env.get("ADB_SHELL_TIMEOUT_S", _SHELL_TIMEOUT_S)),
        transfer_timeout_s=float(env.get("ADB_TRANSFER_TIMEOUT_S", _TRANSFER_TIMEOUT_S)),
    )


def _smb(config: SmbConfig) -> SmbClient:
    client = SmbClient(config)
    client.configure()
    return client


def _devices() -> DeviceStore:
    return DeviceStore(_DEVICES_YAML)


def _run(job_type: OperationType, device_ip: str, job_fn: Any) -> str | None:
    """Run one job synchronously in-process, echoing its log as it completes.

    RAISES:
        click.ClickException: If the job failed.
    """
    registry = OperationRegistry(NullOperationSink())
    op_id = "cli"
    registry.start(op_id, job_type, device_ip)
    run_job(registry, _STAGING_ROOT, op_id, job_fn)
    op = registry.get(op_id)
    for entry in op.logs:
        click.echo(f"[*] {entry['message']}")
    if op.status == OperationStatus.FAILED:
        raise click.ClickException(op.result or "Job failed")
    return op.result


@click.group()
def main() -> None:
    """Firestick maintenance and Kodi deployment tool."""


@main.command()
def download() -> None:
    """Download the latest stable Kodi APK and publish it as the gold base image."""
    config = _build_config()
    result = _run(OperationType.FETCH, "", functools.partial(_fetch_base_job.run_fetch_base, smb=_smb(config), config=config))
    click.echo(f"[+++] {result}")


@main.command()
@click.argument("ip", required=False)
@click.option("--batch", is_flag=True, help="Run on all known devices")
def maintain(ip: str | None, batch: bool) -> None:
    """Debloat, speed up, block telemetry, and clean cache on a device."""
    targets = [d.ip for d in _devices().list()] if batch else [ip]
    if not targets or not targets[0]:
        raise click.UsageError("Provide an IP or use --batch")
    keys = _adb_keys()
    for target_ip in targets:
        click.echo(f"[*] Maintaining {target_ip}...")
        _run(OperationType.MAINTAIN, target_ip, functools.partial(_maintain_job.run_maintain, ip=target_ip, adb_keys=keys))


@main.command()
@click.argument("ip", required=False)
@click.option("--batch", is_flag=True, help="Run on all known devices")
@click.option("--backup", default=None, help="Specific backup reference to deploy (device_dir/filename.tar.gz)")
def deploy(ip: str | None, batch: bool, backup: str | None) -> None:
    """Deploy a backup (or the device's latest one) from the SMB share."""
    device_store = _devices()
    targets = [d.ip for d in device_store.list()] if batch else [ip]
    if not targets or not targets[0]:
        raise click.UsageError("Provide an IP or use --batch")
    config = _build_config()
    keys = _adb_keys()
    smb = _smb(config)

    apk_cache_dir = Path(tempfile.mkdtemp(prefix="deploy_apk_", dir=str(_STAGING_ROOT)))
    try:
        base_apk_local = _deploy_job.resolve_base_apk(apk_cache_dir, smb, config)
        for target_ip in targets:
            click.echo(f"[*] Deploying to {target_ip}...")
            result = _run(OperationType.DEPLOY, target_ip, functools.partial(
                _deploy_job.run_deploy, ip=target_ip, backup_name=backup,
                devices=device_store, adb_keys=keys, smb=smb, config=config,
                base_apk_local=base_apk_local,
            ))
            click.echo(f"[+++] {result}")
    finally:
        shutil.rmtree(apk_cache_dir, ignore_errors=True)


@main.command()
@click.argument("ip")
@click.option("--name", default=None, help="Custom name for the backup")
def capture(ip: str, name: str | None) -> None:
    """Capture a device's Kodi config and upload it to the SMB share."""
    config = _build_config()
    result = _run(OperationType.CAPTURE, ip, functools.partial(
        _capture_job.run_capture, ip=ip, backup_name=name,
        devices=_devices(), adb_keys=_adb_keys(), smb=_smb(config), config=config,
    ))
    click.echo(f"[+++] {result}")


@main.command(name="list-backups")
def list_backups() -> None:
    """List available backups on the SMB share."""
    config = _build_config()
    if not config.has_smb:
        click.echo("[!] SMB is not configured — set SMB_USER/SMB_PASS in .env")
        return
    service = FleetService(config, _devices(), OperationRegistry(NullOperationSink()), _smb(config), _adb_keys(), _STAGING_ROOT)
    backups = service.list_backups()
    if not backups:
        click.echo("[!] No backups found on SMB share.")
        return
    click.echo(f"[*] Backups on //{config.smb_host}/{config.smb_share}/{config.smb_backup_dir}:")
    for bak in backups:
        click.echo(f"  {bak['filename']}  {bak['date']}  {bak['size']} bytes")


@main.command()
@click.option("--subnet", default="192.168.50", help="Network subnet to scan (e.g. 192.168.1)")
def scan(subnet: str) -> None:
    """Scan the network for Firesticks and update the device inventory."""
    keys = _adb_keys()
    result = _run(OperationType.SCAN, subnet, functools.partial(
        _scan_job.run_scan, subnet=subnet, devices=_devices(), adb_runner=AdbShellRunner(keys),
    ))
    click.echo(f"[+++] {result}")


@main.command(name="apply-display")
@click.argument("ip")
@click.option("--resolution-index", type=int, default=None, help="Kodi videoscreen.resolution index")
@click.option("--overscan", nargs=4, type=int, default=None, metavar="LEFT TOP RIGHT BOTTOM")
def apply_display(ip: str, resolution_index: int | None, overscan: tuple[int, int, int, int] | None) -> None:
    """Patch resolution/overscan calibration onto an already-deployed device."""
    settings: dict[str, Any] = {}
    if resolution_index is not None:
        settings["resolution_index"] = resolution_index
    if overscan is not None:
        left, top, right, bottom = overscan
        settings["overscan"] = {"left": left, "top": top, "right": right, "bottom": bottom}
    if not settings:
        raise click.UsageError("Provide --resolution-index and/or --overscan")
    result = _run(OperationType.DISPLAY, ip, functools.partial(
        _display_job.run_apply_display, ip=ip, display_settings=settings, adb_keys=_adb_keys(),
    ))
    click.echo(f"[+++] {result}")


if __name__ == "__main__":
    main()

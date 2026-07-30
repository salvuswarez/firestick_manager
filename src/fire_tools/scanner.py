"""Network scanner for Firetools devices."""
from __future__ import annotations

import logging
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)

_PING_WORKERS = 50
_ADB_WORKERS = 20
_PING_TIMEOUT = 1


class Scanner:
    """Parallel ping sweep + ADB discovery for a /24 IPv4 subnet."""

    def __init__(
        self,
        subnet: str,
        adb_runner: Callable[[str, str], str],
    ) -> None:
        """Initialize the scanner.

        **PARAMETERS:**
        - subnet: First three octets of the IPv4 subnet (e.g., "192.168.50").
        - adb_runner: Callable(ip, cmd) -> str used to run ADB commands.
          Required — keeps this module importable and testable without a
          Home Assistant environment (no import of the package `__init__`).
        """
        self.subnet = subnet
        self.adb_runner = adb_runner

    def _prefix(self) -> str:
        """Normalize the subnet string to a three-octet prefix.

        **RETURNS:**
        A subnet prefix string like "192.168.50".
        """
        prefix = self.subnet
        if prefix.endswith("/24"):
            prefix = prefix[:-3]
        if prefix.endswith(".0"):
            prefix = prefix[:-2]
        return prefix

    def _run_adb(self, ip: str, cmd: str) -> str:
        """Execute an ADB command via the configured runner.

        **PARAMETERS:**
        - ip: IPv4 address of the target device.
        - cmd: ADB shell command to execute.

        **RETURNS:**
        The command output as a string, or an empty string on failure.
        """
        return self.adb_runner(ip, cmd)

    def _ping(self, ip: str) -> str | None:
        """Ping a single host and return the IP if it responds.

        **PARAMETERS:**
        - ip: IPv4 address to ping.

        **RETURNS:**
        The IP string if the host responds, otherwise None.
        """
        system = platform.system()
        if system == "Windows":
            cmd = ["ping", "-n", "1", "-w", "1000", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_PING_TIMEOUT + 1,
            )
            if proc.returncode == 0:
                return ip
        except subprocess.TimeoutExpired:
            LOGGER.debug("Ping timeout for %s", ip)
        except Exception as exc:
            LOGGER.debug("Ping failed for %s: %s", ip, exc)
        return None

    def _ping_sweep(self) -> list[str]:
        """Ping every address in the configured subnet.

        **RETURNS:**
        A list of responsive IPv4 addresses.
        """
        prefix = self._prefix()
        ips = [f"{prefix}.{i}" for i in range(1, 255)]

        with ThreadPoolExecutor(max_workers=_PING_WORKERS) as pool:
            results = pool.map(self._ping, ips)

        return [ip for ip in results if ip]

    def _arp_table(self) -> dict[str, str]:
        """Read the ARP table and return a map of IP to MAC.

        **RETURNS:**
        A dictionary mapping IPv4 address strings to normalized lowercase
        MAC addresses.
        """
        table: dict[str, str] = {}
        try:
            proc = subprocess.run(
                ["arp", "-a"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = proc.stdout
        except Exception as exc:
            LOGGER.warning("ARP lookup failed: %s", exc)
            return table

        for line in output.splitlines():
            ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
            if not ip_match:
                continue
            mac_match = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", line)
            if not mac_match:
                continue
            ip = ip_match.group(1)
            mac = mac_match.group(0).replace("-", ":").lower()
            table[ip] = mac
        return table

    def _probe_adb(self, ip: str, mac: str) -> dict[str, Any] | None:
        """Collect device metadata via ADB.

        **PARAMETERS:**
        - ip: IPv4 address of the host.
        - mac: MAC address discovered from ARP (may be empty).

        **RETURNS:**
        A device dict with ip, mac, name, model, serial, and android_version,
        or None if the device does not expose a product model.
        """
        device_name = self._run_adb(ip, "settings get global device_name").strip()
        if not device_name or device_name.lower() == "null":
            device_name = self._run_adb(ip, "getprop ro.product.model").strip()
        model = self._run_adb(ip, "getprop ro.product.model").strip()
        if not model:
            return None
        serial = self._run_adb(ip, "getprop ro.serialno").strip()
        android_version = self._run_adb(ip, "getprop ro.build.version.release").strip()
        return {
            "ip": ip,
            "mac": mac,
            "name": device_name,
            "model": model,
            "serial": serial,
            "android_version": android_version,
        }

    def scan(self) -> list[dict[str, Any]]:
        """Scan the subnet and return discovered devices.

        **RETURNS:**
        A list of device dictionaries containing ip, mac, name, model,
        serial, and android_version.
        """
        hosts = self._ping_sweep()
        arp_table = self._arp_table()
        discovered: list[dict[str, Any]] = []

        def _probe(ip: str) -> dict[str, Any] | None:
            mac = arp_table.get(ip, "")
            return self._probe_adb(ip, mac)

        with ThreadPoolExecutor(max_workers=_ADB_WORKERS) as pool:
            for result in pool.map(_probe, hosts):
                if result:
                    discovered.append(result)

        return discovered

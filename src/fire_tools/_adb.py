"""ADB transport: one cached key pair, one connection per job.

The original code loaded and parsed the RSA signer, then opened a fresh
TCP+auth handshake, on *every* shell command — a maintenance pass issuing
~35 commands paid ~35 handshakes. `AdbClient` holds one connection for the
life of a job; `AdbKeyStore` loads the signer once and caches it.
"""
from __future__ import annotations

import io
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .const import ADB_PORT

LOGGER = logging.getLogger(__name__)


class AdbError(Exception):
    """Base error for ADB communication failures."""


class AdbCommandError(AdbError):
    """An ADB shell command failed, or the connection dropped mid-command.

    Deliberately distinct from "command ran and produced no output" — the
    original code collapsed both cases to `""`, which is how a dropped
    connection during a destructive command could look identical to success.
    """


class AdbRunner(Protocol):
    """Structural type for the simple `(ip, cmd) -> str` callable Scanner needs."""

    def __call__(self, ip: str, cmd: str) -> str: ...


class AdbKeyStore:
    """Loads or generates the ADB RSA key pair once and caches the signer.

    PARAMETERS:
        key_dir (Path): Directory holding `adbkey` / `adbkey.pub`. Should live
            outside the git-tracked integration directory (e.g. under
            `hass.config.path(".firetools")`), since the private key is a
            standing authorization token for every paired device.
    """

    def __init__(self, key_dir: Path) -> None:
        self._key_dir = key_dir
        self._signer: Any = None

    def signer(self) -> Any:
        """Return the cached `PythonRSASigner`, generating a key pair if needed.

        RETURNS:
            PythonRSASigner: Signer used to authenticate ADB connections.
        """
        if self._signer is not None:
            return self._signer

        from adb_shell.auth.keygen import keygen
        from adb_shell.auth.sign_pythonrsa import PythonRSASigner

        self._key_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._key_dir, stat.S_IRWXU)  # 0o700
        key_path = self._key_dir / "adbkey"
        pub_path = self._key_dir / "adbkey.pub"

        if not key_path.exists() or not pub_path.exists():
            LOGGER.info("Generating ADB RSA key pair at %s", key_path)
            keygen(str(key_path))
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

        with open(key_path, encoding="utf-8") as f:
            priv = f.read()
        with open(pub_path, encoding="utf-8") as f:
            pub = f.read()

        self._signer = PythonRSASigner(pub, priv)
        return self._signer


class AdbClient:
    """One ADB connection to a single device, held open for a whole job.

    Use as a context manager so the handshake happens once per job rather
    than once per command:

        with AdbClient(ip, key_store) as client:
            client.shell("...")
            client.shell("...")

    PARAMETERS:
        ip (str): Device IPv4 address.
        key_store (AdbKeyStore): Shared signer cache.
        port (int): ADB port. Defaults to `ADB_PORT`.
        transport_timeout_s (float): Per-command transport timeout.
        auth_timeout_s (float): Auth handshake timeout.
    """

    def __init__(
        self,
        ip: str,
        key_store: AdbKeyStore,
        port: int = ADB_PORT,
        transport_timeout_s: float = 30.0,
        auth_timeout_s: float = 10.0,
    ) -> None:
        self._ip = ip
        self._key_store = key_store
        self._port = port
        self._transport_timeout_s = transport_timeout_s
        self._auth_timeout_s = auth_timeout_s
        self._device: Any = None

    def __enter__(self) -> AdbClient:
        from adb_shell.adb_device import AdbDeviceTcp

        self._device = AdbDeviceTcp(
            self._ip, self._port, default_transport_timeout_s=self._transport_timeout_s
        )
        self._device.connect(rsa_keys=[self._key_store.signer()], auth_timeout_s=self._auth_timeout_s)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                LOGGER.debug("Error closing ADB connection to %s", self._ip, exc_info=True)

    def shell(self, cmd: str) -> str:
        """Run a shell command and raise if it fails.

        PARAMETERS:
            cmd (str): Shell command to execute on the device.

        RETURNS:
            str: Command output, stripped.

        RAISES:
            AdbCommandError: If the command could not be executed (dropped
                connection, timeout, device error) — never returned as an
                empty string, so callers cannot mistake failure for success.
        """
        try:
            output = self._device.shell(cmd)
        except Exception as exc:
            raise AdbCommandError(f"ADB command failed for {self._ip} ({cmd}): {exc}") from exc
        LOGGER.debug("ADB ok %s (%s): %s", self._ip, cmd, (output or "").strip()[:200])
        return output.strip() if output else ""

    def shell_ok(self, cmd: str) -> str:
        """Run a shell command, returning `""` on failure instead of raising.

        Use only for informational reads (e.g. `getprop`) where "no output"
        and "failed" are both acceptable outcomes for the caller.

        PARAMETERS:
            cmd (str): Shell command to execute on the device.

        RETURNS:
            str: Command output, or `""` if the command failed.
        """
        try:
            return self.shell(cmd)
        except AdbCommandError as exc:
            LOGGER.warning("%s", exc)
            return ""

    def pull(self, remote_path: str, local_path: str) -> None:
        """Pull a file from the device.

        RAISES:
            AdbCommandError: If the pull fails.
        """
        try:
            buf = io.BytesIO()
            self._device.pull(remote_path, buf)
            with open(local_path, "wb") as f:
                f.write(buf.getvalue())
        except Exception as exc:
            raise AdbCommandError(f"ADB pull failed for {self._ip} ({remote_path}): {exc}") from exc

    def push_file(self, local_path: str, remote_path: str) -> None:
        """Push a single file to the device.

        RAISES:
            AdbCommandError: If the push fails.
        """
        try:
            with open(local_path, "rb") as f:
                buf = io.BytesIO(f.read())
            self._device.push(buf, remote_path)
        except Exception as exc:
            raise AdbCommandError(f"ADB push failed for {self._ip} ({remote_path}): {exc}") from exc

    def push_tree(self, local_dir: str, remote_dir: str) -> None:
        """Recursively push a local directory to the device.

        This is the operation the original single-file `_adb_push` could
        not perform — deploy previously tried to push extracted backup
        folders (`addons/`, `userdata/`, `media/`) through a file-only push
        and silently failed on every one.

        PARAMETERS:
            local_dir (str): Local directory to push.
            remote_dir (str): Destination directory on the device.

        RAISES:
            AdbCommandError: If creating the remote directory or any file
                push fails.
        """
        self.shell(f"mkdir -p {remote_dir}")
        for root, _dirs, files in os.walk(local_dir):
            rel = os.path.relpath(root, local_dir)
            remote_root = remote_dir if rel == "." else f"{remote_dir}/{rel.replace(os.sep, '/')}"
            if rel != ".":
                self.shell(f"mkdir -p {remote_root}")
            for name in files:
                self.push_file(os.path.join(root, name), f"{remote_root}/{name}")


@dataclass(frozen=True, slots=True)
class AdbShellRunner:
    """`(ip, cmd) -> str` adapter satisfying `Scanner`'s `adb_runner` seam.

    Opens one short-lived connection per probed host and swallows failures
    to `""`, matching the "not a real device" semantics `Scanner._probe_adb`
    expects — a non-responding host should be dropped from the scan, not
    raise.
    """

    key_store: AdbKeyStore

    def __call__(self, ip: str, cmd: str) -> str:
        try:
            with AdbClient(ip, self.key_store, transport_timeout_s=10.0) as client:
                return client.shell_ok(cmd)
        except AdbError:
            return ""

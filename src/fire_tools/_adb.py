"""ADB transport: one cached key pair, one connection per job.

The original code loaded and parsed the RSA signer, then opened a fresh
TCP+auth handshake, on *every* shell command — a maintenance pass issuing
~35 commands paid ~35 handshakes. `AdbClient` holds one connection for the
life of a job; `AdbKeyStore` loads the signer once and caches it.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shlex
import socket
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .const import ADB_PORT

LOGGER = logging.getLogger(__name__)

# adb_shell's AdbDeviceTcp.shell()/pull()/push() each take their own
# transport_timeout_s/read_timeout_s per call — they do NOT inherit the
# connection-level default_transport_timeout_s set at construction, and
# fall back to the library's own 10s default if not passed explicitly.
# 10s is fine for most shell commands but not guaranteed for a slower one
# (e.g. `tar czf` over a large userdata dir), and is far too short for a
# multi-hundred-MB backup transfer — which is exactly what timed out mid-pull.
_SHELL_TIMEOUT_S = 60.0
_TRANSFER_TIMEOUT_S = 180.0

# Uploads go over a netcat stream rather than adb_shell's push(). Measured
# 2026-08-01 against a real Fire TV: adb_shell push moved *zero* bytes and
# hung until timeout for anything over a few MB (the destination file was
# never even created), while the same host reached ~12 MB/s over netcat.
# adb_shell's shell() and pull() are unaffected and still used as-is.
_NC_PORT = 5599
_NC_CHUNK = 262144
_NC_CONNECT_TIMEOUT_S = 30.0
# Cap on how long to wait for the device to finish writing what was already
# streamed. Only covers the flush after the last byte is sent, not the
# transfer itself.
_NC_SETTLE_TIMEOUT_S = 120.0
# The listener's shell command blocks for the whole transfer, so its timeout
# has to cover a worst-case upload rather than a single round-trip.
_NC_LISTENER_TIMEOUT_S = 3600.0


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
    """Shared ADB session config: the cached RSA signer plus connection timeouts.

    The signer and the timeouts are bundled here rather than threaded as
    separate parameters through every `AdbClient(...)` call site (jobs/*.py,
    service.py, `AdbShellRunner`) — this object is already constructed once,
    in the one place each consumer (CLI, HA integration) resolves its own
    config (`.env`, or `entry.data`/`entry.options`), and passed everywhere
    ADB is used.

    PARAMETERS:
        key_dir (Path): Directory holding `adbkey` / `adbkey.pub`. Should live
            outside the git-tracked integration directory (e.g. under
            `hass.config.path(".firetools")`), since the private key is a
            standing authorization token for every paired device.
        shell_timeout_s (float): Default transport/read timeout for
            `AdbClient.shell()` calls. adb_shell's own default (10s) can be
            too short for a slower command (e.g. `tar czf` over a large
            userdata dir).
        transfer_timeout_s (float): Default transport/read timeout for
            `AdbClient.pull()`/`push_file()` — needs to cover an entire
            backup archive transfer, not just a single protocol round-trip.
    """

    def __init__(
        self,
        key_dir: Path,
        shell_timeout_s: float = _SHELL_TIMEOUT_S,
        transfer_timeout_s: float = _TRANSFER_TIMEOUT_S,
    ) -> None:
        self._key_dir = key_dir
        self._signer: Any = None
        self.shell_timeout_s = shell_timeout_s
        self.transfer_timeout_s = transfer_timeout_s

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
        """Connect to the device.

        RAISES:
            AdbCommandError: If the connection or auth handshake fails —
                e.g. the host isn't listening on the ADB port (very common
                mid-scan, when most probed IPs won't be Fire TV devices at
                all). Previously this let adb_shell's/socket's raw exception
                escape uncaught, which crashed `Scanner.scan()`'s whole
                thread pool on the first non-responsive host instead of
                just skipping it.
        """
        self._connect()
        return self

    def _connect(self) -> None:
        from adb_shell.adb_device import AdbDeviceTcp

        try:
            self._device = AdbDeviceTcp(self._ip, self._port, default_transport_timeout_s=self._transport_timeout_s)
            self._device.connect(rsa_keys=[self._key_store.signer()], auth_timeout_s=self._auth_timeout_s)
        except Exception as exc:
            raise AdbCommandError(f"ADB connect failed for {self._ip}: {exc}") from exc

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                LOGGER.debug("Error closing ADB connection to %s", self._ip, exc_info=True)

    def shell(self, cmd: str, timeout_s: float | None = None) -> str:
        """Run a shell command and raise if it fails.

        PARAMETERS:
            cmd (str): Shell command to execute on the device.
            timeout_s (float | None): Override for this call's transport/read
                timeout. Defaults to `AdbKeyStore.shell_timeout_s`. Pass a
                larger value for a command whose duration scales with data
                size rather than being a quick fixed-cost operation (e.g.
                `tar czf` over a large userdata dir) — capture.py's tar step
                previously used the flat 60s default and could silently
                truncate the archive on a slower/larger device.

        RETURNS:
            str: Command output, stripped.

        RAISES:
            AdbCommandError: If the command could not be executed (dropped
                connection, timeout, device error) — never returned as an
                empty string, so callers cannot mistake failure for success.
        """
        try:
            timeout = timeout_s if timeout_s is not None else self._key_store.shell_timeout_s
            output = self._device.shell(cmd, transport_timeout_s=timeout, read_timeout_s=timeout)
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
            timeout = self._key_store.transfer_timeout_s
            buf = io.BytesIO()
            self._device.pull(remote_path, buf, transport_timeout_s=timeout, read_timeout_s=timeout)
            with open(local_path, "wb") as f:
                f.write(buf.getvalue())
        except Exception as exc:
            raise AdbCommandError(f"ADB pull failed for {self._ip} ({remote_path}): {exc}") from exc

    def push_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file to the device over a netcat stream, verifying the result.

        `adb_shell`'s own `push()` is not used: against a real Fire TV it moves
        zero bytes and hangs for anything beyond a few MB (see `_NC_PORT`). The
        device listens with `toybox nc` and this streams into it over a plain
        socket, which measured ~12 MB/s on the same host that `push()` stalled on.

        The transferred file is always md5-checked. `nc` exits as soon as it
        sees the connection close and silently drops whatever is still in its
        receive buffer, so a naive send loses the tail — the digest is what
        makes a short write an error instead of a corrupt deploy.

        **PARAMETERS:**
            `local_path` (str): File to upload.  <br>
            `remote_path` (str): Destination path on the device.  <br>

        **RAISES:**
            `AdbCommandError`: If the listener can't start, the stream fails, the
                device never finishes writing, or the digest doesn't match.  <br>
        """
        path = Path(local_path)
        size = path.stat().st_size
        expected = _file_md5(path)
        quoted_remote = shlex.quote(remote_path)

        self.shell_ok(f"rm -f {quoted_remote}")
        listener = _NcListener(self._ip, self._key_store, self._port, remote_path)
        listener.start()
        try:
            self._stream_to_device(path, size, remote_path)
        except OSError as exc:
            raise AdbCommandError(f"Netcat push failed for {self._ip} ({remote_path}): {exc}") from exc
        finally:
            listener.stop()

        actual = self.shell_ok(f"md5sum {quoted_remote}")[:32]
        if actual != expected:
            landed = self._remote_size(remote_path)
            raise AdbCommandError(
                f"Netcat push corrupted for {self._ip} ({remote_path}): " f"expected md5 {expected} of {size} bytes, got {actual or 'none'} of {landed} bytes"
            )
        LOGGER.debug("Pushed %s to %s:%s (%d bytes, md5 ok)", local_path, self._ip, remote_path, size)

    def _stream_to_device(self, path: Path, size: int, remote_path: str) -> None:
        """Stream `path` to the waiting `nc` listener and wait for it to land.

        Waits for the device-side file to reach `size` before closing rather
        than sleeping a fixed interval — closing early is exactly what makes
        `nc` drop its buffered tail.
        """
        sock = self._connect_to_listener()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(_NC_CHUNK)
                    if not chunk:
                        break
                    sock.sendall(chunk)
            self._await_remote_size(remote_path, size)
            sock.shutdown(socket.SHUT_WR)
        finally:
            sock.close()

    def _connect_to_listener(self) -> socket.socket:
        """Connect to the device's `nc`, retrying while it finishes binding.

        The port is deliberately not probed first: `nc -l` accepts exactly one
        connection, so a probe would consume the listener this push needs.

        **RETURNS:**
            `socket.socket`: Connected socket.  <br>

        **RAISES:**
            `OSError`: If the listener never came up.  <br>
        """
        deadline = time.monotonic() + _NC_CONNECT_TIMEOUT_S
        last: OSError | None = None
        while time.monotonic() < deadline:
            try:
                return socket.create_connection((self._ip, _NC_PORT), timeout=_NC_CONNECT_TIMEOUT_S)
            except OSError as exc:
                last = exc
                time.sleep(0.25)
        raise last or OSError(f"netcat listener never came up on {self._ip}:{_NC_PORT}")

    def _await_remote_size(self, remote_path: str, size: int) -> None:
        """Block until the device-side file has `size` bytes, or time out.

        A timeout is logged rather than raised — `push_file`'s digest check is
        the authority on whether the transfer actually succeeded.
        """
        deadline = time.monotonic() + _NC_SETTLE_TIMEOUT_S
        landed = -1
        while time.monotonic() < deadline:
            landed = self._remote_size(remote_path)
            if landed >= size:
                return
            time.sleep(0.5)
        LOGGER.warning("Device %s stopped at %d/%d bytes for %s", self._ip, landed, size, remote_path)

    def _remote_size(self, remote_path: str) -> int:
        """RETURNS: int: Size of `remote_path` on the device, or -1 if unknown."""
        out = self.shell_ok(f"stat -c %s {shlex.quote(remote_path)}").strip()
        return int(out) if out.isdigit() else -1

    def free_bytes(self, remote_dir: str) -> int:
        """Report free space on the filesystem holding `remote_dir`.

        Used to bail out before pushing an archive that wouldn't fit rather
        than filling the device and failing mid-extract.

        **PARAMETERS:**
            `remote_dir` (str): Any path on the filesystem to measure.  <br>

        **RETURNS:**
            `int`: Free bytes, or ``0`` if `df` output couldn't be parsed.  <br>
        """
        output = self.shell_ok(f"df -k {shlex.quote(remote_dir)}")
        lines = output.splitlines()
        if len(lines) < 2:
            return 0
        parts = lines[-1].split()
        for value in reversed(parts):
            if value.isdigit():
                return int(value) * 1024
        return 0


class _NcListener:
    """Runs `toybox nc -l` on the device for the lifetime of one push.

    The listener cannot simply be backgrounded with `&`: `adb_shell` closes the
    shell stream as soon as the command returns and the device tears the whole
    process group down with it, so the listener dies before anything connects
    (confirmed against a real device — `nohup` and `setsid` don't save it
    either). Instead the command is left *running* on its own connection, held
    open by a worker thread, and exits naturally when the transfer's socket
    closes.

    **PARAMETERS:**
        `ip` (str): Device IPv4 address.  <br>
        `key_store` (AdbKeyStore): Shared signer cache.  <br>
        `port` (int): ADB port.  <br>
        `remote_path` (str): File the listener writes into.  <br>
    """

    def __init__(self, ip: str, key_store: AdbKeyStore, port: int, remote_path: str) -> None:
        self._ip = ip
        self._key_store = key_store
        self._port = port
        self._remote_path = remote_path
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"nc-listener-{ip}")
        self._error: Exception | None = None

    def start(self) -> None:
        """Open the listener's connection and start waiting for the transfer."""
        self._thread.start()

    def stop(self) -> None:
        """Wait for the listener to exit now that the transfer socket is closed."""
        self._thread.join(timeout=_NC_SETTLE_TIMEOUT_S)
        if self._error is not None:
            LOGGER.debug("Netcat listener on %s ended with: %s", self._ip, self._error)

    def _run(self) -> None:
        cmd = f"toybox nc -l -p {_NC_PORT} > {shlex.quote(self._remote_path)}"
        try:
            with AdbClient(self._ip, self._key_store, port=self._port) as client:
                # Blocks until the sender closes the socket; the timeout has to
                # cover the whole transfer, not a single round-trip.
                client.shell(cmd, timeout_s=_NC_LISTENER_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - surfaced via the digest check
            self._error = exc


def _file_md5(path: Path) -> str:
    """RETURNS: str: Hex md5 of `path`, read in chunks so a multi-hundred-MB
    archive never lands in memory whole."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_NC_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        except AdbError as exc:
            # Debug, not warning: during a subnet scan the overwhelming
            # majority of probed IPs simply aren't listening on 5555 at all,
            # so this fires constantly by design. But when a *known* Fire TV
            # doesn't show up in scan results, this is the only trace of why —
            # previously this was fully silent, indistinguishable from "not
            # a device" and "device errored," making that exact case
            # undiagnosable without guessing.
            LOGGER.debug("Scan probe failed for %s (%s): %s", ip, cmd, exc)
            return ""

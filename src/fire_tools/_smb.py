"""Thin SMB wrapper around `smbclient`, configured for one host/share.

Single place that builds UNC paths and talks to the share — jobs and the
operation sink depend on this instead of calling `smbclient` directly with
hand-built `\\\\host\\share\\...` strings scattered across the codebase.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterator, TypeVar

import smbclient
from smbprotocol.exceptions import SMBConnectionClosed

from .models import SmbConfig

LOGGER = logging.getLogger(__name__)

_CHUNK_SIZE = 65536
_T = TypeVar("_T")
_RETRYABLE = (SMBConnectionClosed, ConnectionError, BrokenPipeError)


class SmbClient:
    """SMB access scoped to one configured host/share.

    PARAMETERS:
        config (SmbConfig): Resolved SMB host/share/credentials.
    """

    def __init__(self, config: SmbConfig) -> None:
        self._config = config

    def configure(self) -> None:
        """(Re)initialize the shared `smbclient` connection cache and credentials."""
        if not self._config.has_smb:
            return
        smbclient.reset_connection_cache()
        smbclient.ClientConfig(username=self._config.smb_user, password=self._config.smb_pass)
        LOGGER.info("SMB client configured for //%s/%s", self._config.smb_host, self._config.smb_share)

    def reset(self) -> None:
        """Tear down the shared connection cache (called on integration unload)."""
        smbclient.reset_connection_cache()

    def _call_with_retry(self, fn: Callable[[], _T]) -> _T:
        """Run `fn`, retrying once against a fresh connection on a stale-socket error.

        `smbclient` caches connections internally and opens them lazily on
        first use. A connection left idle long enough for the server to
        close it (e.g. while a slow non-SMB step like an HTTP download runs
        with no SMB traffic) fails with `SMBConnectionClosed` on the next
        call, even though nothing about this specific operation is wrong.
        One retry after resetting the cache is enough to recover.

        **PARAMETERS:**
        - fn: Zero-argument callable performing the SMB operation.

        **RETURNS:**
        Whatever `fn` returns.
        """
        try:
            return fn()
        except _RETRYABLE as exc:
            LOGGER.warning("SMB connection stale, reconnecting and retrying: %s", exc)
            self.configure()
            return fn()

    def path(self, remote: str) -> str:
        """RETURNS: str: Full UNC path for `remote` under the configured share.

        `remote` is normalized to backslashes first — callers build it with
        forward slashes (e.g. `f"{backup_dir}/{device_dir}"`), and mixing
        that with the UNC prefix's backslashes produced paths `smbclient`
        could not resolve past the first directory level
        (STATUS_OBJECT_PATH_NOT_FOUND on a directory that genuinely exists).
        """
        normalized = remote.replace("/", "\\")
        return f"\\\\{self._config.smb_host}\\{self._config.smb_share}\\{normalized}"

    def makedirs(self, remote: str) -> None:
        """Create `remote` (and parents) on the share if it does not exist."""
        self._call_with_retry(lambda: smbclient.makedirs(self.path(remote), exist_ok=True))

    def write_text(self, remote: str, text: str) -> None:
        """Write `text` to `remote`, creating parent directories as needed."""

        def _write() -> None:
            with smbclient.open_file(self.path(remote), mode="w") as f:
                f.write(text)

        self._call_with_retry(_write)

    def read_text(self, remote: str) -> str:
        """RETURNS: str: Contents of `remote`.

        RAISES:
            OSError: If `remote` does not exist or cannot be read.
        """

        def _read() -> str:
            with smbclient.open_file(self.path(remote), mode="r") as f:
                content = f.read()
            return content.decode("utf-8") if isinstance(content, bytes) else content

        return self._call_with_retry(_read)

    def upload_file(self, local_path: str, remote: str) -> int:
        """Upload a local file to `remote`, chunked.

        RETURNS:
            int: Number of bytes uploaded.
        """

        def _upload() -> int:
            size = 0
            with open(local_path, "rb") as src, smbclient.open_file(self.path(remote), mode="wb") as dst:
                while True:
                    chunk = src.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    dst.write(chunk)
                    size += len(chunk)
            return size

        return self._call_with_retry(_upload)

    def download_file(self, remote: str, local_path: str) -> None:
        """Download `remote` to `local_path`, chunked.

        RAISES:
            OSError: If `remote` does not exist or cannot be read.
        """

        def _download() -> None:
            with smbclient.open_file(self.path(remote), mode="rb") as src, open(local_path, "wb") as dst:
                while True:
                    chunk = src.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    dst.write(chunk)

        self._call_with_retry(_download)

    def scandir(self, remote: str) -> list:
        """List directory entries under `remote`.

        Deliberately materializes the listing *inside* the retry wrapper.
        `smbclient.scandir` is a generator, so returning it unconsumed meant
        `_call_with_retry` only guarded generator *creation* — a connection
        going stale during iteration raised outside the retry, where callers
        that catch broadly (e.g. `FleetService._list_backups_in`) turned it
        into a silently short listing. That surfaced as backups randomly
        missing from `list-backups` and from the HA panel's backup picker.

        RETURNS:
            list: `smbclient.scandir` entries under `remote`.
        """
        return self._call_with_retry(lambda: list(smbclient.scandir(self.path(remote))))

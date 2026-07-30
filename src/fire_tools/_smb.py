"""Thin SMB wrapper around `smbclient`, configured for one host/share.

Single place that builds UNC paths and talks to the share — jobs and the
operation sink depend on this instead of calling `smbclient` directly with
hand-built `\\\\host\\share\\...` strings scattered across the codebase.
"""
from __future__ import annotations

import logging
from typing import Iterator

import smbclient

from .models import SmbConfig

LOGGER = logging.getLogger(__name__)

_CHUNK_SIZE = 65536


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

    def path(self, remote: str) -> str:
        """RETURNS: str: Full UNC path for `remote` under the configured share."""
        return f"\\\\{self._config.smb_host}\\{self._config.smb_share}\\{remote}"

    def makedirs(self, remote: str) -> None:
        """Create `remote` (and parents) on the share if it does not exist."""
        smbclient.makedirs(self.path(remote), exist_ok=True)

    def write_text(self, remote: str, text: str) -> None:
        """Write `text` to `remote`, creating parent directories as needed."""
        with smbclient.open_file(self.path(remote), mode="w") as f:
            f.write(text)

    def read_text(self, remote: str) -> str:
        """RETURNS: str: Contents of `remote`.

        RAISES:
            OSError: If `remote` does not exist or cannot be read.
        """
        with smbclient.open_file(self.path(remote), mode="r") as f:
            content = f.read()
        return content.decode("utf-8") if isinstance(content, bytes) else content

    def upload_file(self, local_path: str, remote: str) -> int:
        """Upload a local file to `remote`, chunked.

        RETURNS:
            int: Number of bytes uploaded.
        """
        size = 0
        with open(local_path, "rb") as src, smbclient.open_file(self.path(remote), mode="wb") as dst:
            while True:
                chunk = src.read(_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                size += len(chunk)
        return size

    def download_file(self, remote: str, local_path: str) -> None:
        """Download `remote` to `local_path`, chunked.

        RAISES:
            OSError: If `remote` does not exist or cannot be read.
        """
        with smbclient.open_file(self.path(remote), mode="rb") as src, open(local_path, "wb") as dst:
            while True:
                chunk = src.read(_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)

    def scandir(self, remote: str) -> Iterator:
        """RETURNS: Iterator: `smbclient.scandir` entries under `remote`."""
        return smbclient.scandir(self.path(remote))

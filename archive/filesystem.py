"""
Local filesystem implementation of the immutable SEC dataset archive layer.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from archive.interface import (
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    SECArchiveInterface,
)


class FilesystemSECArchive(SECArchiveInterface):
    """
    Local filesystem backend for storing immutable SEC bulk dataset archives.
    Stores ZIP archive files alongside sidecar JSON metadata manifests.
    """

    def __init__(self, base_path: str = "data/archive") -> None:
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def _normalize_period(self, period: str) -> str:
        p = str(period).strip().upper()
        if not p:
            raise ValueError("Period cannot be empty.")
        return p

    def _zip_path(self, period: str) -> str:
        norm_p = self._normalize_period(period)
        return os.path.join(self.base_path, f"{norm_p}.zip")

    def _manifest_path(self, period: str) -> str:
        norm_p = self._normalize_period(period)
        return os.path.join(self.base_path, f"{norm_p}.json")

    def exists(self, period: str) -> bool:
        z_path = self._zip_path(period)
        m_path = self._manifest_path(period)
        return os.path.exists(z_path) and os.path.exists(m_path)

    def delete_incomplete_archive(self, period: str) -> bool:
        """
        Safely remove a genuinely incomplete archive for period (ZIP exists without manifest,
        or manifest exists without ZIP).

        Refuses to delete/recover a complete archive (where both ZIP and manifest exist).
        Returns True if an incomplete component was removed, False if period was clean.
        """
        norm_period = self._normalize_period(period)
        z_path = self._zip_path(norm_period)
        m_path = self._manifest_path(norm_period)

        z_exists = os.path.exists(z_path)
        m_exists = os.path.exists(m_path)

        if z_exists and m_exists:
            raise ArchiveExistsError(
                f"Cannot delete or recover complete archive for period '{norm_period}'. "
                f"Both ZIP ({z_path}) and manifest ({m_path}) exist intact."
            )

        if not z_exists and not m_exists:
            return False

        removed = False
        if z_exists:
            os.remove(z_path)
            removed = True
        if m_exists:
            os.remove(m_path)
            removed = True

        return removed

    def _compute_sha256(self, content: Union[str, bytes, bytearray]) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        if isinstance(content, str):
            with open(content, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
        elif isinstance(content, (bytes, bytearray)):
            hasher.update(content)
            size = len(content)
        else:
            raise TypeError("content must be a file path string or bytes/bytearray.")

        return hasher.hexdigest(), size

    def put(
        self,
        period: str,
        content: Union[str, bytes, bytearray],
        metadata: Optional[ArchiveMetadata] = None,
    ) -> ArchiveMetadata:
        norm_period = self._normalize_period(period)
        zip_file = self._zip_path(norm_period)
        manifest_file = self._manifest_path(norm_period)
        rel_zip_key = f"{norm_period}.zip"

        zip_exists = os.path.exists(zip_file)
        manifest_exists = os.path.exists(manifest_file)

        calc_sha256, calc_size = self._compute_sha256(content)

        if zip_exists and manifest_exists:
            existing_meta = self.metadata(norm_period)
            if existing_meta.sha256 == calc_sha256:
                return existing_meta
            else:
                raise ArchiveExistsError(
                    f"Archive for period '{norm_period}' already exists with different SHA-256 "
                    f"({existing_meta.sha256} vs incoming {calc_sha256}). Immutable archives cannot be overwritten."
                )
        elif zip_exists and not manifest_exists:
            raise ArchiveExistsError(
                f"Incomplete archive state for period '{norm_period}': ZIP archive exists but manifest is missing. "
                f"Overwriting incomplete archives is forbidden."
            )
        elif manifest_exists and not zip_exists:
            raise ArchiveExistsError(
                f"Incomplete archive state for period '{norm_period}': Manifest exists but ZIP archive is missing. "
                f"Recreating incomplete archives is forbidden."
            )

        # Write ZIP content
        if isinstance(content, str):
            shutil.copy2(content, zip_file)
        else:
            with open(zip_file, "wb") as f:
                f.write(content)

        retrieved_at = datetime.now(timezone.utc).isoformat()

        if metadata is None:
            final_meta = ArchiveMetadata(
                period=norm_period,
                source="SEC",
                source_url="",
                sha256=calc_sha256,
                retrieved_at=retrieved_at,
                archive_path=rel_zip_key,
                validation_status="validated",
                file_size_bytes=calc_size,
            )
        else:
            final_meta = ArchiveMetadata(
                period=norm_period,
                source=metadata.source or "SEC",
                source_url=metadata.source_url or "",
                sha256=calc_sha256,
                retrieved_at=metadata.retrieved_at or retrieved_at,
                archive_path=rel_zip_key,
                validation_status=metadata.validation_status or "validated",
                file_size_bytes=calc_size,
            )

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(final_meta.to_dict(), f, indent=2)

        return final_meta

    def get(self, period: str) -> bytes:
        if not self.exists(period):
            raise ArchiveNotFoundError(f"Archive for period '{period}' does not exist.")
        zip_file = self._zip_path(period)
        with open(zip_file, "rb") as f:
            return f.read()

    def metadata(self, period: str) -> ArchiveMetadata:
        if not self.exists(period):
            raise ArchiveNotFoundError(f"Archive for period '{period}' does not exist.")
        manifest_file = self._manifest_path(period)
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ArchiveMetadata.from_dict(data)

    def checksum(self, period: str) -> str:
        return self.metadata(period).sha256

    def list(self) -> List[str]:
        periods = []
        for fname in os.listdir(self.base_path):
            if fname.endswith(".json"):
                period = fname[:-5]
                z_file = os.path.join(self.base_path, f"{period}.zip")
                if os.path.exists(z_file):
                    periods.append(period)
        periods.sort()
        return periods

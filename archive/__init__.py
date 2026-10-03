"""
Provider-agnostic SEC quarterly dataset archive abstraction.
"""

from __future__ import annotations

from typing import Optional

from archive.filesystem import FilesystemSECArchive
from archive.interface import (
    ArchiveError,
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    SECArchiveInterface,
)


def get_archive_backend(
    backend_type: str = "filesystem",
    archive_path: str = "data/archive",
) -> SECArchiveInterface:
    """
    Factory to retrieve configured SEC dataset archive backend instance.
    """
    b_type = (backend_type or "filesystem").strip().lower()
    if b_type == "filesystem":
        return FilesystemSECArchive(base_path=archive_path)
    else:
        raise ValueError(f"Unsupported archive backend type: '{backend_type}'")


__all__ = [
    "ArchiveMetadata",
    "ArchiveError",
    "ArchiveExistsError",
    "ArchiveNotFoundError",
    "SECArchiveInterface",
    "FilesystemSECArchive",
    "get_archive_backend",
]

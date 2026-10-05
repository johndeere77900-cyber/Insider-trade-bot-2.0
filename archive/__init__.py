"""
Provider-agnostic SEC quarterly dataset archive abstraction.
"""

from __future__ import annotations

from typing import Any, Optional

from archive.filesystem import FilesystemSECArchive
from archive.interface import (
    ArchiveError,
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    SECArchiveInterface,
)
from archive.s3 import S3SECArchive


def get_archive_backend(
    backend_type: str = "filesystem",
    archive_path: str = "data/archive",
    **kwargs: Any,
) -> SECArchiveInterface:
    """
    Factory to retrieve configured SEC dataset archive backend instance.
    """
    b_type = (backend_type or "filesystem").strip().lower()
    if b_type == "filesystem":
        return FilesystemSECArchive(base_path=archive_path)
    elif b_type in ("s3", "r2", "object_storage", "objectstorage", "s3_compat"):
        return S3SECArchive(**kwargs)
    else:
        raise ValueError(f"Unsupported archive backend type: '{backend_type}'")


__all__ = [
    "ArchiveMetadata",
    "ArchiveError",
    "ArchiveExistsError",
    "ArchiveNotFoundError",
    "SECArchiveInterface",
    "FilesystemSECArchive",
    "S3SECArchive",
    "get_archive_backend",
]

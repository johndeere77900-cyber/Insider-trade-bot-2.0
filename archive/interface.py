"""
Interface and metadata definition for the immutable SEC dataset archive layer.

The archive layer stores original SEC bulk zip files and their associated
durable metadata manifests. It is backend-agnostic (supporting filesystem,
and expandable to cloud object storage backends such as S3, R2, GCS).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


class ArchiveError(Exception):
    """Base exception for archive operations."""


class ArchiveExistsError(ArchiveError):
    """Raised when an attempt is made to overwrite an existing archive record with different content."""


class ArchiveNotFoundError(ArchiveError):
    """Raised when a requested period is not found in the archive."""


@dataclass
class ArchiveMetadata:
    """
    Durable metadata representation for an archived SEC quarterly dataset.
    """
    period: str
    source: str = "SEC"
    source_url: str = ""
    sha256: str = ""
    retrieved_at: str = ""
    archive_path: str = ""
    validation_status: str = "validated"
    file_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ArchiveMetadata:
        return cls(
            period=str(data.get("period", "")),
            source=str(data.get("source", "SEC")),
            source_url=str(data.get("source_url", "")),
            sha256=str(data.get("sha256", "")),
            retrieved_at=str(data.get("retrieved_at", "")),
            archive_path=str(data.get("archive_path", "")),
            validation_status=str(data.get("validation_status", "validated")),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
        )


class SECArchiveInterface(ABC):
    """
    Provider-agnostic interface for storing and retrieving immutable SEC quarterly dataset archives.
    """

    @abstractmethod
    def exists(self, period: str) -> bool:
        """Return True if an archived ZIP exists for the given period."""

    @abstractmethod
    def put(
        self,
        period: str,
        content: Union[str, bytes, bytearray],
        metadata: Optional[ArchiveMetadata] = None,
        overwrite: bool = False,
    ) -> ArchiveMetadata:
        """
        Store an original SEC archive ZIP and its metadata.

        Immutability rule:
        - If period does not exist: store ZIP and manifest.
        - If period exists and content SHA-256 matches existing: idempotent success.
        - If period exists and content SHA-256 differs: raise ArchiveExistsError unless overwrite=True.
        """

    @abstractmethod
    def get(self, period: str) -> bytes:
        """
        Retrieve original SEC quarterly ZIP bytes for period.
        Raises ArchiveNotFoundError if missing.
        """

    @abstractmethod
    def metadata(self, period: str) -> ArchiveMetadata:
        """
        Retrieve ArchiveMetadata manifest for period.
        Raises ArchiveNotFoundError if missing.
        """

    @abstractmethod
    def checksum(self, period: str) -> str:
        """
        Return the SHA-256 checksum of the archived ZIP for period.
        Raises ArchiveNotFoundError if missing.
        """

    @abstractmethod
    def list(self) -> List[str]:
        """Return a sorted list of archived dataset period strings (e.g., ['2006-Q1', '2006-Q2'])."""

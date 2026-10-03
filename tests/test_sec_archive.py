"""
Unit tests for provider-agnostic immutable SEC quarterly dataset archive.
"""

from __future__ import annotations

import os
import zipfile
import pytest

from archive import (
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    FilesystemSECArchive,
    get_archive_backend,
)


def create_dummy_zip(zip_path: str, content_map: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for fname, data in content_map.items():
            zf.writestr(fname, data)


def test_archive_put_and_get(tmp_path) -> None:
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    zip_file = tmp_path / "test_2006Q1.zip"
    create_dummy_zip(str(zip_file), {"SUBMISSION.tsv": "ACCESSION_NUMBER\t12345"})

    meta = ArchiveMetadata(
        period="2006-Q1",
        source="SEC",
        source_url="https://sec.gov/test.zip",
    )

    saved_meta = archive.put("2006-Q1", str(zip_file), metadata=meta)

    assert archive.exists("2006-Q1")
    assert saved_meta.period == "2006-Q1"
    assert saved_meta.source == "SEC"
    assert len(saved_meta.sha256) == 64
    assert saved_meta.file_size_bytes > 0

    zip_bytes = archive.get("2006-Q1")
    assert len(zip_bytes) == saved_meta.file_size_bytes
    assert archive.checksum("2006-Q1") == saved_meta.sha256


def test_archive_idempotency_and_immutability(tmp_path) -> None:
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    zip_file1 = tmp_path / "test1.zip"
    create_dummy_zip(str(zip_file1), {"SUBMISSION.tsv": "SAME_CONTENT"})

    saved_meta1 = archive.put("2006-Q1", str(zip_file1))

    # Identical content write -> Idempotent success
    saved_meta2 = archive.put("2006-Q1", str(zip_file1))
    assert saved_meta1.sha256 == saved_meta2.sha256

    # Different content write -> ArchiveExistsError
    zip_file2 = tmp_path / "test2.zip"
    create_dummy_zip(str(zip_file2), {"SUBMISSION.tsv": "DIFFERENT_CONTENT"})

    with pytest.raises(ArchiveExistsError, match="already exists with different SHA-256"):
        archive.put("2006-Q1", str(zip_file2))


def test_archive_metadata_and_list(tmp_path) -> None:
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    z1 = tmp_path / "q1.zip"
    z2 = tmp_path / "q2.zip"
    create_dummy_zip(str(z1), {"file": "1"})
    create_dummy_zip(str(z2), {"file": "2"})

    archive.put("2006-Q1", str(z1))
    archive.put("2006-Q2", str(z2))

    listed = archive.list()
    assert listed == ["2006-Q1", "2006-Q2"]

    meta1 = archive.metadata("2006-Q1")
    assert meta1.period == "2006-Q1"


def test_archive_missing_handling(tmp_path) -> None:
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    assert archive.exists("2099-Q4") is False

    with pytest.raises(ArchiveNotFoundError):
        archive.get("2099-Q4")

    with pytest.raises(ArchiveNotFoundError):
        archive.metadata("2099-Q4")

    with pytest.raises(ArchiveNotFoundError):
        archive.checksum("2099-Q4")


def test_archive_factory() -> None:
    backend = get_archive_backend("filesystem", "data/archive")
    assert isinstance(backend, FilesystemSECArchive)

    with pytest.raises(ValueError, match="Unsupported archive backend type"):
        get_archive_backend("invalid_type")

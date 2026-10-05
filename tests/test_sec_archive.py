"""
Unit tests for provider-agnostic immutable SEC quarterly dataset archive.
"""

from __future__ import annotations

import json
import os
import zipfile
import pytest

from archive import (
    ArchiveError,
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    FilesystemSECArchive,
    S3SECArchive,
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

    # 1. Both exist with identical SHA-256 -> Idempotent success
    saved_meta2 = archive.put("2006-Q1", str(zip_file1))
    assert saved_meta1.sha256 == saved_meta2.sha256
    assert saved_meta2.archive_path == "2006-Q1.zip"

    # 2. Both exist with different SHA-256 -> ArchiveExistsError
    zip_file2 = tmp_path / "test2.zip"
    create_dummy_zip(str(zip_file2), {"SUBMISSION.tsv": "DIFFERENT_CONTENT"})

    with pytest.raises(ArchiveExistsError, match="already exists with different SHA-256"):
        archive.put("2006-Q1", str(zip_file2))

    # 3. ZIP exists but manifest missing -> ArchiveExistsError (do NOT overwrite)
    zip_only_period = "2006-Q2"
    z_file = archive_dir / f"{zip_only_period}.zip"
    z_file.write_bytes(b"dummy zip content")

    with pytest.raises(ArchiveExistsError, match="ZIP archive exists but manifest is missing"):
        archive.put(zip_only_period, str(zip_file1))

    # 4. Manifest exists but ZIP missing -> ArchiveExistsError (do NOT recreate)
    manifest_only_period = "2006-Q3"
    m_file = archive_dir / f"{manifest_only_period}.json"
    m_file.write_text('{"period": "2006-Q3", "sha256": "abc"}')

    with pytest.raises(ArchiveExistsError, match="Manifest exists but ZIP archive is missing"):
        archive.put(manifest_only_period, str(zip_file1))


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
    backend_fs = get_archive_backend("filesystem", "data/archive")
    assert isinstance(backend_fs, FilesystemSECArchive)

    backend_s3 = get_archive_backend("s3", bucket="my-sec-bucket")
    assert isinstance(backend_s3, S3SECArchive)

    backend_obj = get_archive_backend("object_storage", bucket="my-sec-bucket")
    assert isinstance(backend_obj, S3SECArchive)

    with pytest.raises(ValueError, match="Unsupported archive backend type"):
        get_archive_backend("invalid_type")


def test_s3_archive_requires_bucket_config() -> None:
    s3_backend = S3SECArchive(bucket="")
    with pytest.raises(ArchiveError, match="requires bucket to be configured"):
        s3_backend.exists("2006-Q1")


def test_s3_archive_mock_operations(tmp_path) -> None:
    # Test S3SECArchive using mock client
    store = {}

    class MockBody:
        def __init__(self, content: bytes):
            self._content = content

        def read(self) -> bytes:
            return self._content

    class MockS3Client:
        def head_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound")
            return {}

        def put_object(self, Bucket: str, Key: str, Body: bytes):
            store[Key] = Body

        def get_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound")
            return {"Body": MockBody(store[Key])}

        def get_paginator(self, operation_name: str):
            class MockPaginator:
                def paginate(self, Bucket: str, Prefix: str):
                    contents = [{"Key": k} for k in store.keys() if k.startswith(Prefix)]
                    return [{"Contents": contents}]
            return MockPaginator()

    mock_client = MockS3Client()
    s3_backend = S3SECArchive(bucket="test-bucket", prefix="sec-archives", s3_client=mock_client)

    z1 = tmp_path / "s3_test.zip"
    create_dummy_zip(str(z1), {"file.tsv": "data"})

    meta = s3_backend.put("2006-Q1", str(z1))
    assert s3_backend.exists("2006-Q1") is True
    assert meta.period == "2006-Q1"
    assert s3_backend.get("2006-Q1") == z1.read_bytes()
    assert s3_backend.checksum("2006-Q1") == meta.sha256
    assert s3_backend.list() == ["2006-Q1"]

    # Idempotent put
    meta2 = s3_backend.put("2006-Q1", str(z1))
    assert meta2.sha256 == meta.sha256

    # Differing put raises ArchiveExistsError
    z2 = tmp_path / "s3_diff.zip"
    create_dummy_zip(str(z2), {"file.tsv": "different_data"})

    with pytest.raises(ArchiveExistsError):
        s3_backend.put("2006-Q1", str(z2))

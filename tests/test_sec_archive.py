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


def test_s3_archive_cases_a_through_f(tmp_path) -> None:
    # Verify cases A through F for S3/R2 archive backend
    store = {}
    fail_manifest_write = False

    class MockBody:
        def __init__(self, content: bytes):
            self._content = content

        def read(self) -> bytes:
            return self._content

    class MockS3Client:
        def head_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound 404")
            return {}

        def put_object(self, Bucket: str, Key: str, Body: bytes):
            nonlocal fail_manifest_write
            if fail_manifest_write and Key.endswith(".json"):
                raise ArchiveError("Simulated network failure on manifest upload")
            store[Key] = Body

        def delete_object(self, Bucket: str, Key: str):
            if Key in store:
                del store[Key]

        def get_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound 404")
            return {"Body": MockBody(store[Key])}

        def get_paginator(self, operation_name: str):
            class MockPaginator:
                def paginate(self, Bucket: str, Prefix: str):
                    contents = [{"Key": k} for k in store.keys() if k.startswith(Prefix)]
                    return [{"Contents": contents}]
            return MockPaginator()

    mock_client = MockS3Client()
    s3_backend = S3SECArchive(bucket="insider-trade-sec-archive", prefix="sec-archives", s3_client=mock_client)

    z1 = tmp_path / "z1.zip"
    create_dummy_zip(str(z1), {"SUBMISSION.tsv": "DATA1"})

    # CASE A: Neither exists -> upload both ZIP and metadata
    period_a = "2006-Q1"
    meta_a = s3_backend.put(period_a, str(z1))
    assert s3_backend.exists(period_a) is True
    assert f"sec-archives/{period_a}.zip" in store
    assert f"sec-archives/{period_a}.json" in store

    # CASE B: Both exist and SHA matches -> idempotent return
    meta_b = s3_backend.put(period_a, str(z1))
    assert meta_b.sha256 == meta_a.sha256

    # CASE C: Both exist and SHA differs -> ArchiveExistsError
    z2 = tmp_path / "z2.zip"
    create_dummy_zip(str(z2), {"SUBMISSION.tsv": "DIFFERENT_DATA2"})
    with pytest.raises(ArchiveExistsError, match="already exists with different SHA-256"):
        s3_backend.put(period_a, str(z2))

    # CASE D: ZIP exists but metadata does not -> reject; never overwrite
    period_d = "2006-Q2"
    store[f"sec-archives/{period_d}.zip"] = b"ZIP_ONLY_CONTENT"
    with pytest.raises(ArchiveExistsError, match="ZIP archive exists but manifest is missing"):
        s3_backend.put(period_d, str(z1))

    # CASE E: Metadata exists but ZIP does not -> reject; never overwrite
    period_e = "2006-Q3"
    store[f"sec-archives/{period_e}.json"] = b'{"sha256": "abc"}'
    with pytest.raises(ArchiveExistsError, match="Manifest exists but ZIP archive is missing"):
        s3_backend.put(period_e, str(z1))

    # CASE F: ZIP upload succeeds but metadata upload fails -> next retry detects partial state and rejects overwrite
    period_f = "2006-Q4"
    fail_manifest_write = True
    with pytest.raises(ArchiveError, match="Simulated network failure"):
        s3_backend.put(period_f, str(z1))

    # ZIP was uploaded before manifest failure occurred
    assert f"sec-archives/{period_f}.zip" in store
    assert f"sec-archives/{period_f}.json" not in store

    # On next retry, Case D prevents overwriting incomplete archive
    fail_manifest_write = False
    with pytest.raises(ArchiveExistsError, match="ZIP archive exists but manifest is missing"):
        s3_backend.put(period_f, str(z1))

    # Test controlled recovery of incomplete archive
    # Complete archive cannot be recovered/deleted
    with pytest.raises(ArchiveExistsError, match="Cannot delete or recover complete archive"):
        s3_backend.delete_incomplete_archive(period_a)

    # Incomplete archive (Case F) can be safely deleted
    assert s3_backend.delete_incomplete_archive(period_f) is True
    assert f"sec-archives/{period_f}.zip" not in store

    # Clean upload succeeds after recovery
    meta_recovered = s3_backend.put(period_f, str(z1))
    assert meta_recovered.period == period_f
    assert s3_backend.exists(period_f) is True


def test_s3_strict_error_classification(tmp_path) -> None:
    # Test that 403 / AccessDenied or network errors raise ArchiveError and are NOT converted to missing object
    class MockErrorS3Client:
        def head_object(self, Bucket: str, Key: str):
            raise Exception("403 AccessDenied")

    mock_client = MockErrorS3Client()
    s3_backend = S3SECArchive(bucket="insider-trade-sec-archive", s3_client=mock_client)

    with pytest.raises(ArchiveError, match="403 AccessDenied"):
        s3_backend.exists("2006-Q1")


def test_s3_archive_configuration_environment_wiring(monkeypatch) -> None:
    monkeypatch.setenv("SEC_ARCHIVE_BUCKET", "env-bucket")
    monkeypatch.setenv("SEC_ARCHIVE_PREFIX", "custom-prefix")
    monkeypatch.setenv("SEC_ARCHIVE_ENDPOINT_URL", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setenv("AWS_REGION", "auto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret456")

    archive = S3SECArchive()
    assert archive.bucket == "env-bucket"
    assert archive.prefix == "custom-prefix/"
    assert archive._endpoint_url == "https://account.r2.cloudflarestorage.com"
    assert archive._region_name == "auto"
    assert archive._aws_access_key_id == "key123"
    assert archive._aws_secret_access_key == "secret456"

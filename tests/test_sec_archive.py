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

    # 3. ZIP exists but manifest missing -> Same SHA completes manifest safely
    zip_only_period = "2006-Q2"
    z_file = archive_dir / f"{zip_only_period}.zip"
    z_file.write_bytes(zip_file1.read_bytes())
    assert archive.is_incomplete(zip_only_period) is True

    m_completed = archive.put(zip_only_period, str(zip_file1))
    assert m_completed.period == zip_only_period
    assert archive.exists(zip_only_period) is True

    # 3b. Incomplete ZIP exists with DIFFERENT SHA -> Rejects with ArchiveExistsError (immutability)
    incomplete_diff_period = "2006-Q4"
    diff_zip_file = archive_dir / f"{incomplete_diff_period}.zip"
    diff_zip_file.write_bytes(zip_file1.read_bytes())
    assert archive.is_incomplete(incomplete_diff_period) is True

    with pytest.raises(ArchiveExistsError, match="Conflicting incomplete archives cannot be overwritten"):
        archive.put(incomplete_diff_period, str(zip_file2))

    # 4. Manifest exists but ZIP missing -> Differing SHA rejects with ArchiveExistsError and preserves manifest
    manifest_only_period = "2006-Q3"
    m_file = archive_dir / f"{manifest_only_period}.json"
    m_file.write_text('{"period": "2006-Q3", "sha256": "abc"}')
    assert archive.is_incomplete(manifest_only_period) is True

    with pytest.raises(ArchiveExistsError, match="Conflicting manifest cannot be overwritten"):
        archive.put(manifest_only_period, str(zip_file1))

    # Assert manifest still exists and SHA remains intact
    assert m_file.exists() is True
    data = json.loads(m_file.read_text())
    assert data["sha256"] == "abc"

    # 4b. Manifest exists but ZIP missing -> Matching SHA safely completes archive
    m_matching_period = "2006-Q4"
    m_file_match = archive_dir / f"{m_matching_period}.json"
    calc_sha = saved_meta1.sha256
    m_file_match.write_text(f'{{"period": "{m_matching_period}", "sha256": "{calc_sha}"}}')

    m_recreated = archive.put(m_matching_period, str(zip_file1))
    assert m_recreated.period == m_matching_period
    assert archive.exists(m_matching_period) is True


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


def test_filesystem_get_incomplete_zip(tmp_path):
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    zip_file = tmp_path / "orphan.zip"
    create_dummy_zip(
        str(zip_file),
        {"SUBMISSION.tsv": "ORPHAN"},
    )

    orphan_path = archive_dir / "2006-Q1.zip"
    orphan_path.write_bytes(zip_file.read_bytes())

    assert archive.is_incomplete("2006-Q1") is True
    assert archive.get_incomplete_zip("2006-Q1") == zip_file.read_bytes()


def test_archive_missing_handling(tmp_path) -> None:
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    assert archive.exists("2099-Q4") is False

    with pytest.raises(ArchiveNotFoundError):
        archive.get("2099-Q4")

    with pytest.raises(ArchiveNotFoundError):
        archive.get_incomplete_zip("2099-Q4")

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

        def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs):
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

    # CASE D: ZIP exists but metadata does not -> if SHA matches, completes manifest
    period_d = "2006-Q2"
    store[f"sec-archives/{period_d}.zip"] = z1.read_bytes()
    assert s3_backend.is_incomplete(period_d) is True
    assert s3_backend.get_incomplete_zip(period_d) == z1.read_bytes()
    meta_d = s3_backend.put(period_d, str(z1))
    assert meta_d.period == period_d
    assert s3_backend.exists(period_d) is True

    # Test missing ZIP raises ArchiveNotFoundError in get_incomplete_zip
    with pytest.raises(ArchiveNotFoundError):
        s3_backend.get_incomplete_zip("2099-Q4")

    # CASE E: Metadata exists but ZIP does not -> differing SHA rejects with ArchiveExistsError
    period_e = "2006-Q3"
    store[f"sec-archives/{period_e}.json"] = b'{"sha256": "abc"}'
    assert s3_backend.is_incomplete(period_e) is True
    with pytest.raises(ArchiveExistsError, match="Conflicting manifest cannot be overwritten"):
        s3_backend.put(period_e, str(z1))

    # CASE E2: Metadata exists but ZIP does not -> matching SHA safely completes archive
    period_e2 = "2006-Q4"
    matching_meta_json = json.dumps({"sha256": meta_a.sha256}).encode("utf-8")
    store[f"sec-archives/{period_e2}.json"] = matching_meta_json
    assert s3_backend.is_incomplete(period_e2) is True
    meta_e = s3_backend.put(period_e2, str(z1))
    assert meta_e.period == period_e2
    assert s3_backend.exists(period_e2) is True

    # CASE F: ZIP upload succeeds but metadata upload fails -> next retry completes manifest safely
    period_f = "2007-Q1"
    fail_manifest_write = True
    with pytest.raises(ArchiveError, match="Simulated network failure"):
        s3_backend.put(period_f, str(z1))

    # ZIP was uploaded before manifest failure occurred
    assert f"sec-archives/{period_f}.zip" in store
    assert f"sec-archives/{period_f}.json" not in store
    assert s3_backend.is_incomplete(period_f) is True

    # On next retry, put with matching SHA completes manifest safely
    fail_manifest_write = False
    meta_f = s3_backend.put(period_f, str(z1))
    assert meta_f.period == period_f
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

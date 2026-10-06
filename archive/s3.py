"""
Object storage (S3 / S3-compatible) implementation of the immutable SEC dataset archive layer.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from archive.interface import (
    ArchiveError,
    ArchiveExistsError,
    ArchiveMetadata,
    ArchiveNotFoundError,
    SECArchiveInterface,
)


def _is_not_found_exception(exc: Exception) -> bool:
    """
    Return True strictly if exc represents an S3 object-not-found error (404/NoSuchKey/NotFound).
    Any non-404 error (e.g. 403 AccessDenied, network error, throttling) returns False.
    """
    try:
        from botocore.exceptions import ClientError
        if isinstance(exc, ClientError):
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error_code in {"404", "NoSuchKey", "NotFound"} or http_status == 404:
                return True
            return False
    except ImportError:
        pass

    exc_str = str(exc).lower()
    if "404" in exc_str or "nosuchkey" in exc_str or "notfound" in exc_str or "not found" in exc_str:
        return True

    return False


class S3SECArchive(SECArchiveInterface):
    """
    Object-storage backend (AWS S3, Cloudflare R2, MinIO, GCS S3 API)
    for storing immutable SEC bulk dataset archives.
    Stores quarterly ZIP archive files alongside sidecar JSON metadata manifests.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        prefix: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        s3_client: Optional[Any] = None,
    ) -> None:
        self.bucket = bucket or os.getenv("SEC_ARCHIVE_BUCKET", "")
        p = prefix if prefix is not None else os.getenv("SEC_ARCHIVE_PREFIX", "sec-archives/")
        if p and not p.endswith("/"):
            p += "/"
        self.prefix = p

        self._endpoint_url = endpoint_url or os.getenv("SEC_ARCHIVE_ENDPOINT_URL")
        self._region_name = region_name or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULTREGION") or "auto"
        self._aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self._aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self._client = s3_client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.bucket:
            raise ArchiveError(
                "S3 archive backend requires bucket to be configured via SEC_ARCHIVE_BUCKET or constructor."
            )

        try:
            import boto3
        except ImportError as exc:
            raise ArchiveError(
                "boto3 package is required for S3 object storage backend."
            ) from exc

        kwargs: Dict[str, Any] = {}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        if self._region_name:
            kwargs["region_name"] = self._region_name
        if self._aws_access_key_id and self._aws_secret_access_key:
            kwargs["aws_access_key_id"] = self._aws_access_key_id
            kwargs["aws_secret_access_key"] = self._aws_secret_access_key

        try:
            self._client = boto3.client("s3", **kwargs)
        except Exception as exc:
            raise ArchiveError(f"Failed to initialize S3 client: {exc}") from exc

        return self._client

    def _normalize_period(self, period: str) -> str:
        p = str(period).strip().upper()
        if not p:
            raise ValueError("Period cannot be empty.")
        return p

    def _zip_key(self, period: str) -> str:
        norm_p = self._normalize_period(period)
        return f"{self.prefix}{norm_p}.zip"

    def _manifest_key(self, period: str) -> str:
        norm_p = self._normalize_period(period)
        return f"{self.prefix}{norm_p}.json"

    def _object_exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if _is_not_found_exception(exc):
                return False
            raise ArchiveError(
                f"S3 head_object error for bucket '{self.bucket}', key '{key}': {exc}"
            ) from exc

    def exists(self, period: str) -> bool:
        z_key = self._zip_key(period)
        m_key = self._manifest_key(period)
        return self._object_exists(z_key) and self._object_exists(m_key)

    def is_incomplete(self, period: str) -> bool:
        norm_period = self._normalize_period(period)
        zip_key = self._zip_key(norm_period)
        manifest_key = self._manifest_key(norm_period)
        z_exists = self._object_exists(zip_key)
        m_exists = self._object_exists(manifest_key)
        return (z_exists and not m_exists) or (m_exists and not z_exists)

    def delete_incomplete_archive(self, period: str) -> bool:
        """
        Safely remove a genuinely incomplete archive for period (ZIP exists without manifest,
        or manifest exists without ZIP).

        Refuses to delete/recover a complete archive (where both ZIP and manifest exist).
        Returns True if an incomplete component was removed, False if period was clean.
        """
        norm_period = self._normalize_period(period)
        zip_key = self._zip_key(norm_period)
        manifest_key = self._manifest_key(norm_period)

        zip_exists = self._object_exists(zip_key)
        manifest_exists = self._object_exists(manifest_key)

        if zip_exists and manifest_exists:
            raise ArchiveExistsError(
                f"Cannot delete or recover complete archive for period '{norm_period}'. "
                f"Both ZIP ({zip_key}) and manifest ({manifest_key}) exist intact."
            )

        if not zip_exists and not manifest_exists:
            return False

        client = self._get_client()
        removed = False

        if zip_exists:
            try:
                client.delete_object(Bucket=self.bucket, Key=zip_key)
                removed = True
            except Exception as exc:
                raise ArchiveError(
                    f"Failed to delete incomplete ZIP object '{zip_key}' in bucket '{self.bucket}': {exc}"
                ) from exc

        if manifest_exists:
            try:
                client.delete_object(Bucket=self.bucket, Key=manifest_key)
                removed = True
            except Exception as exc:
                raise ArchiveError(
                    f"Failed to delete incomplete manifest object '{manifest_key}' in bucket '{self.bucket}': {exc}"
                ) from exc

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
        zip_key = self._zip_key(norm_period)
        manifest_key = self._manifest_key(norm_period)

        zip_exists = self._object_exists(zip_key)
        manifest_exists = self._object_exists(manifest_key)

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
            client = self._get_client()
            try:
                existing_obj = client.get_object(Bucket=self.bucket, Key=zip_key)
                existing_bytes = existing_obj["Body"].read()
                existing_sha, _ = self._compute_sha256(existing_bytes)
            except Exception:
                existing_sha = None

            if existing_sha == calc_sha256:
                pass
            else:
                self.delete_incomplete_archive(norm_period)
        elif manifest_exists and not zip_exists:
            self.delete_incomplete_archive(norm_period)

        # Upload ZIP bytes
        if isinstance(content, str):
            with open(content, "rb") as f:
                zip_bytes = f.read()
        else:
            zip_bytes = bytes(content)

        client = self._get_client()
        try:
            client.put_object(Bucket=self.bucket, Key=zip_key, Body=zip_bytes)
        except Exception as exc:
            raise ArchiveError(f"Failed to upload ZIP archive key '{zip_key}' in bucket '{self.bucket}': {exc}") from exc

        retrieved_at = datetime.now(timezone.utc).isoformat()

        if metadata is None:
            final_meta = ArchiveMetadata(
                period=norm_period,
                source="SEC",
                source_url="",
                sha256=calc_sha256,
                retrieved_at=retrieved_at,
                archive_path=zip_key,
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
                archive_path=zip_key,
                validation_status=metadata.validation_status or "validated",
                file_size_bytes=calc_size,
            )

        manifest_bytes = json.dumps(final_meta.to_dict(), indent=2).encode("utf-8")
        try:
            client.put_object(Bucket=self.bucket, Key=manifest_key, Body=manifest_bytes)
        except Exception as exc:
            raise ArchiveError(f"Failed to upload manifest key '{manifest_key}' in bucket '{self.bucket}': {exc}") from exc

        return final_meta

    def get(self, period: str) -> bytes:
        if not self.exists(period):
            raise ArchiveNotFoundError(f"Archive for period '{period}' does not exist.")
        zip_key = self._zip_key(period)
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=zip_key)
            return response["Body"].read()
        except Exception as exc:
            if _is_not_found_exception(exc):
                raise ArchiveNotFoundError(f"Archive key '{zip_key}' not found in bucket '{self.bucket}'.") from exc
            raise ArchiveError(f"Failed to retrieve archive key '{zip_key}' in bucket '{self.bucket}': {exc}") from exc

    def metadata(self, period: str) -> ArchiveMetadata:
        manifest_key = self._manifest_key(period)
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=manifest_key)
            data = json.loads(response["Body"].read().decode("utf-8"))
            return ArchiveMetadata.from_dict(data)
        except Exception as exc:
            if _is_not_found_exception(exc):
                raise ArchiveNotFoundError(f"Archive metadata key '{manifest_key}' not found in bucket '{self.bucket}'.") from exc
            raise ArchiveError(f"Failed to retrieve metadata key '{manifest_key}' in bucket '{self.bucket}': {exc}") from exc

    def checksum(self, period: str) -> str:
        return self.metadata(period).sha256

    def list(self) -> List[str]:
        client = self._get_client()
        periods = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    if key.endswith(".json"):
                        filename = key[len(self.prefix):] if key.startswith(self.prefix) else key
                        if filename.endswith(".json"):
                            p = filename[:-5]
                            if self._object_exists(self._zip_key(p)):
                                periods.append(p)
        except Exception as exc:
            raise ArchiveError(f"Failed to list object storage archives in bucket '{self.bucket}': {exc}") from exc

        periods.sort()
        return periods

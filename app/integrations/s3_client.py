"""
S3Client: secure outbound connector for image storage in AWS S3.

Provides:
- Image upload with size (5MB) and format (JPEG/PNG) validation.
- Retry with exponential backoff for transient errors (up to 3 attempts).
- Idempotent uploads via deterministic S3 key derived from content hash.
- Presigned URL generation for retrieval.
- Structured error logging for observability.

Configuration is sourced exclusively from environment variables:
- AWS_S3_BUCKET (required)
- AWS_REGION (default: us-east-1)
- AWS_S3_PRESIGNED_URL_EXPIRY_SECONDS (default: 3600)
- AWS_S3_PUBLIC_BASE_URL (optional; if set, public URLs are returned instead of presigned URLs)

Credentials are resolved by boto3's default credential chain, which
includes IAM role credentials when running on AWS infrastructure (ECS
task roles, EC2 instance profiles, EKS IRSA, etc.). No static
credentials are read or embedded here.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("app.integrations.s3_client")

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.2

RETRYABLE_ERROR_CODES = {
    "RequestTimeout",
    "Throttling",
    "ThrottlingException",
    "SlowDown",
    "InternalError",
    "ServiceUnavailable",
    "500",
    "503",
}


class S3ValidationError(ValueError):
    """Raised when an uploaded file fails validation before hitting S3."""


class S3OperationError(RuntimeError):
    """Raised when an S3 operation fails after exhausting retries."""


@dataclass(frozen=True)
class S3Config:
    bucket: str
    region: str
    presigned_expiry_seconds: int
    public_base_url: Optional[str]

    @staticmethod
    def from_env() -> "S3Config":
        bucket = os.environ.get("AWS_S3_BUCKET")
        if not bucket:
            raise S3OperationError(
                "AWS_S3_BUCKET environment variable is required for S3Client"
            )
        region = os.environ.get("AWS_REGION", "us-east-1")
        expiry_raw = os.environ.get("AWS_S3_PRESIGNED_URL_EXPIRY_SECONDS", "3600")
        try:
            expiry = int(expiry_raw)
        except ValueError:
            expiry = 3600
        public_base_url = os.environ.get("AWS_S3_PUBLIC_BASE_URL") or None
        return S3Config(
            bucket=bucket,
            region=region,
            presigned_expiry_seconds=expiry,
            public_base_url=public_base_url,
        )


def _validate_file(file_content: bytes, content_type: str) -> None:
    """Enforce 5MB size limit and JPEG/PNG content-type validation."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise S3ValidationError(
            f"Unsupported image format '{content_type}'. Allowed formats: "
            f"{', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )
    size = len(file_content)
    if size > MAX_IMAGE_SIZE_BYTES:
        raise S3ValidationError(
            f"Image size {size} bytes exceeds the maximum allowed size of "
            f"{MAX_IMAGE_SIZE_BYTES} bytes (5MB)"
        )
    if size == 0:
        raise S3ValidationError("Image file content is empty")


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "")
        status_code = str(
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", "")
        )
        return error_code in RETRYABLE_ERROR_CODES or status_code in RETRYABLE_ERROR_CODES
    if isinstance(exc, BotoCoreError):
        return True
    return False


def _idempotency_key(file_content: bytes, file_name: str) -> str:
    """Derive a deterministic S3 key so repeated uploads of identical
    content are idempotent (same key => same object, no duplicate side
    effects on retry)."""
    digest = hashlib.sha256(file_content).hexdigest()
    _, _, ext = file_name.rpartition(".")
    ext = ext.lower() if ext else "bin"
    return f"images/{digest}.{ext}"


class S3Client:
    """Client wrapper around boto3 S3 for image storage operations."""

    def __init__(self, config: Optional[S3Config] = None, boto_client=None):
        self._config = config or S3Config.from_env()
        self._client = boto_client or boto3.client(
            "s3",
            region_name=self._config.region,
            config=Config(
                retries={"max_attempts": 0},  # we manage retries explicitly
                connect_timeout=5,
                read_timeout=10,
            ),
        )

    def _retry(self, operation_name: str, resource: str, func, *args, **kwargs):
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (ClientError, BotoCoreError) as exc:
                last_exc = exc
                retryable = _is_retryable(exc)
                logger.warning(
                    "S3 operation failed",
                    extra={
                        "operation": operation_name,
                        "resource": resource,
                        "error": str(exc),
                        "attempt": attempt,
                        "max_attempts": MAX_RETRIES,
                        "retryable": retryable,
                    },
                )
                if not retryable or attempt == MAX_RETRIES:
                    break
                time.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        logger.error(
            "S3 operation failed after retries",
            extra={
                "operation": operation_name,
                "resource": resource,
                "error": str(last_exc),
                "attempts": MAX_RETRIES,
            },
        )
        raise S3OperationError(
            f"S3 {operation_name} failed for '{resource}' after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    def upload_file(self, file_content: bytes, file_name: str, content_type: str) -> str:
        """Validate and upload image bytes to S3, returning a retrievable URL.

        Idempotent: identical content maps to the same S3 key, so retries
        (client-side or caller-side) do not create duplicate objects.
        """
        _validate_file(file_content, content_type)
        key = _idempotency_key(file_content, file_name)

        def _put():
            return self._client.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=file_content,
                ContentType=content_type,
            )

        self._retry("upload_file", key, _put)

        logger.info(
            "S3 upload succeeded",
            extra={
                "operation": "upload_file",
                "resource": key,
                "bucket": self._config.bucket,
                "size_bytes": len(file_content),
            },
        )
        return self.get_file_url(key)

    def get_file_url(self, file_name: str) -> str:
        """Return a public URL (if configured) or a presigned URL for the object."""
        if self._config.public_base_url:
            return f"{self._config.public_base_url.rstrip('/')}/{file_name.lstrip('/')}"

        def _generate():
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket, "Key": file_name},
                ExpiresIn=self._config.presigned_expiry_seconds,
            )

        url = self._retry("get_file_url", file_name, _generate)
        logger.info(
            "Generated presigned URL",
            extra={"operation": "get_file_url", "resource": file_name},
        )
        return url

    def check_db_health(self, db) -> bool:
        """Delegates to the shared database health check for a unified
        health surface on this client, per the module's declared
        interface. Uses app.integrations.db_health.check_db_health.
        """
        from app.integrations.db_health import check_db_health as _check

        return _check(db)

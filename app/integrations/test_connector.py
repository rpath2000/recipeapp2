"""
Integration tests for app.integrations.s3_client and app.integrations.db_health.

Covers required test cases:
- S3Client.upload with valid image returns URL
- S3Client.upload with >5MB file raises validation error
- Database health check succeeds when DB is running
- Database health check fails gracefully when DB is unreachable
- S3Client retries transient errors up to 3 times
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.exc import OperationalError

os.environ.setdefault("AWS_S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_REGION", "us-east-1")

from app.integrations.s3_client import (  # noqa: E402
    MAX_IMAGE_SIZE_BYTES,
    S3Client,
    S3Config,
    S3OperationError,
    S3ValidationError,
)
from app.integrations.db_health import check_db_health  # noqa: E402


def _make_client(boto_client) -> S3Client:
    config = S3Config(
        bucket="test-bucket",
        region="us-east-1",
        presigned_expiry_seconds=3600,
        public_base_url=None,
    )
    return S3Client(config=config, boto_client=boto_client)


def _throttling_error(operation_name: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "Throttling", "Message": "Rate exceeded"},
            "ResponseMetadata": {"HTTPStatusCode": 503},
        },
        operation_name=operation_name,
    )


class TestS3ClientUpload:
    def test_upload_valid_image_returns_url(self):
        boto_mock = MagicMock()
        boto_mock.put_object.return_value = {}
        boto_mock.generate_presigned_url.return_value = (
            "https://test-bucket.s3.amazonaws.com/images/abc.jpg?signature=xyz"
        )
        client = _make_client(boto_mock)

        content = b"\xff\xd8\xff" + b"0" * 100  # small fake JPEG payload
        url = client.upload_file(content, "recipe.jpg", "image/jpeg")

        assert url.startswith("https://")
        boto_mock.put_object.assert_called_once()
        call_kwargs = boto_mock.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["ContentType"] == "image/jpeg"
        assert call_kwargs["Body"] == content

    def test_upload_over_5mb_raises_validation_error(self):
        boto_mock = MagicMock()
        client = _make_client(boto_mock)

        oversized_content = b"0" * (MAX_IMAGE_SIZE_BYTES + 1)

        with pytest.raises(S3ValidationError) as exc_info:
            client.upload_file(oversized_content, "big.png", "image/png")

        assert "exceeds the maximum allowed size" in str(exc_info.value)
        boto_mock.put_object.assert_not_called()

    def test_upload_rejects_unsupported_format(self):
        boto_mock = MagicMock()
        client = _make_client(boto_mock)

        with pytest.raises(S3ValidationError) as exc_info:
            client.upload_file(b"gif-bytes", "anim.gif", "image/gif")

        assert "Unsupported image format" in str(exc_info.value)
        boto_mock.put_object.assert_not_called()

    def test_upload_retries_transient_errors_up_to_3_times(self, monkeypatch):
        boto_mock = MagicMock()
        boto_mock.put_object.side_effect = [
            _throttling_error("PutObject"),
            _throttling_error("PutObject"),
            {},  # succeeds on 3rd attempt
        ]
        boto_mock.generate_presigned_url.return_value = "https://presigned.example/url"

        client = _make_client(boto_mock)
        monkeypatch.setattr("app.integrations.s3_client.time.sleep", lambda _: None)

        content = b"\x89PNG" + b"1" * 50
        url = client.upload_file(content, "photo.png", "image/png")

        assert url == "https://presigned.example/url"
        assert boto_mock.put_object.call_count == 3

    def test_upload_exhausts_retries_and_raises_operation_error(self, monkeypatch):
        boto_mock = MagicMock()
        boto_mock.put_object.side_effect = [
            _throttling_error("PutObject"),
            _throttling_error("PutObject"),
            _throttling_error("PutObject"),
        ]
        client = _make_client(boto_mock)
        monkeypatch.setattr("app.integrations.s3_client.time.sleep", lambda _: None)

        content = b"\x89PNG" + b"1" * 50
        with pytest.raises(S3OperationError):
            client.upload_file(content, "photo.png", "image/png")

        assert boto_mock.put_object.call_count == 3

    def test_get_file_url_returns_presigned_url(self):
        boto_mock = MagicMock()
        boto_mock.generate_presigned_url.return_value = (
            "https://test-bucket.s3.amazonaws.com/images/key.jpg?sig=abc"
        )
        client = _make_client(boto_mock)

        url = client.get_file_url("images/key.jpg")

        assert "images/key.jpg" in boto_mock.generate_presigned_url.call_args.kwargs["Params"]["Key"]
        assert url.startswith("https://")

    def test_get_file_url_uses_public_base_url_when_configured(self):
        boto_mock = MagicMock()
        config = S3Config(
            bucket="test-bucket",
            region="us-east-1",
            presigned_expiry_seconds=3600,
            public_base_url="https://cdn.example.com",
        )
        client = S3Client(config=config, boto_client=boto_mock)

        url = client.get_file_url("images/key.jpg")

        assert url == "https://cdn.example.com/images/key.jpg"
        boto_mock.generate_presigned_url.assert_not_called()


class TestDatabaseHealthCheck:
    def test_health_check_succeeds_when_db_is_running(self):
        db_session = MagicMock()
        db_session.execute.return_value = MagicMock()

        result = check_db_health(db_session)

        assert result is True
        db_session.execute.assert_called_once()

    def test_health_check_fails_gracefully_when_db_unreachable(self):
        db_session = MagicMock()
        db_session.execute.side_effect = OperationalError(
            "connection failed", params=None, orig=Exception("could not connect")
        )

        result = check_db_health(db_session)

        assert result is False

    def test_health_check_fails_gracefully_on_unexpected_error(self):
        db_session = MagicMock()
        db_session.execute.side_effect = RuntimeError("unexpected failure")

        result = check_db_health(db_session)

        assert result is False

"""
Unit tests for ImageService covering upload validation (size/format) and
image URL retrieval.
"""
from __future__ import annotations

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.image_service import (
    ALLOWED_CONTENT_TYPES,
    MAX_IMAGE_SIZE_BYTES,
    ImageService,
    ImageValidationError,
)


def _make_upload_file(
    filename: str, content: bytes, content_type: str
) -> UploadFile:
    headers = Headers({"content-type": content_type})
    upload = UploadFile(filename=filename, file=io.BytesIO(content), headers=headers)
    return upload


class FakeS3Client:
    """Test double conforming to the shared S3Client interface."""

    def __init__(self) -> None:
        self.uploaded = {}

    def upload_file(self, file_content: bytes, file_name: str, content_type: str) -> str:
        self.uploaded[file_name] = (file_content, content_type)
        return f"https://fake-bucket.example.com/{file_name}"

    def get_file_url(self, file_name: str) -> str:
        return f"https://fake-bucket.example.com/{file_name}"

    def check_db_health(self, db) -> bool:
        return True


@pytest.fixture()
def service():
    return ImageService()


class TestUploadValidation:
    def test_upload_valid_jpeg_succeeds(self, service):
        content = b"\xff\xd8\xff" + b"0" * 100  # arbitrary bytes, valid size
        file = _make_upload_file("photo.jpg", content, "image/jpeg")

        url = service.upload_image(file, recipe_id="recipe-123")

        assert url is not None
        assert "recipe-123" in url

    def test_upload_valid_png_succeeds(self, service):
        content = b"\x89PNG" + b"0" * 100
        file = _make_upload_file("photo.png", content, "image/png")

        url = service.upload_image(file, recipe_id="recipe-456")

        assert url is not None

    def test_upload_rejects_oversized_file(self, service):
        content = b"0" * (MAX_IMAGE_SIZE_BYTES + 1)
        file = _make_upload_file("big.jpg", content, "image/jpeg")

        with pytest.raises(ImageValidationError) as excinfo:
            service.upload_image(file, recipe_id="recipe-789")

        assert "size" in str(excinfo.value).lower()

    def test_upload_accepts_file_at_exact_max_size(self, service):
        content = b"0" * MAX_IMAGE_SIZE_BYTES
        file = _make_upload_file("exact.jpg", content, "image/jpeg")

        url = service.upload_image(file, recipe_id="recipe-max")

        assert url is not None

    def test_upload_rejects_unsupported_format(self, service):
        content = b"GIF89a" + b"0" * 100
        file = _make_upload_file("animation.gif", content, "image/gif")

        with pytest.raises(ImageValidationError) as excinfo:
            service.upload_image(file, recipe_id="recipe-gif")

        assert "format" in str(excinfo.value).lower()

    def test_upload_rejects_empty_file(self, service):
        file = _make_upload_file("empty.jpg", b"", "image/jpeg")

        with pytest.raises(ImageValidationError):
            service.upload_image(file, recipe_id="recipe-empty")

    def test_upload_requires_recipe_id(self, service):
        content = b"\xff\xd8\xff" + b"0" * 10
        file = _make_upload_file("photo.jpg", content, "image/jpeg")

        with pytest.raises(ImageValidationError):
            service.upload_image(file, recipe_id="")

    def test_upload_delegates_to_injected_s3_client(self):
        fake_s3 = FakeS3Client()
        service = ImageService(s3_client=fake_s3)
        content = b"\xff\xd8\xff" + b"0" * 100
        file = _make_upload_file("photo.jpg", content, "image/jpeg")

        url = service.upload_image(file, recipe_id="recipe-s3")

        assert url.startswith("https://fake-bucket.example.com/")
        assert len(fake_s3.uploaded) == 1

    def test_allowed_content_types_constant_includes_jpeg_and_png(self):
        assert "image/jpeg" in ALLOWED_CONTENT_TYPES
        assert "image/png" in ALLOWED_CONTENT_TYPES


class TestGetImageUrl:
    def test_get_image_url_returns_none_when_not_uploaded(self, service):
        assert service.get_image_url("unknown-recipe") is None

    def test_get_image_url_returns_url_after_upload(self, service):
        content = b"\xff\xd8\xff" + b"0" * 100
        file = _make_upload_file("photo.jpg", content, "image/jpeg")
        uploaded_url = service.upload_image(file, recipe_id="recipe-xyz")

        retrieved_url = service.get_image_url("recipe-xyz")

        assert retrieved_url == uploaded_url

    def test_get_image_url_with_blank_recipe_id_returns_none(self, service):
        assert service.get_image_url("") is None

"""
ImageService: validates and manages recipe image uploads.

Responsible for:
- Validating upload size (<= 5MB) and format (JPEG, PNG only)
- Generating storage references / keys for uploaded images
- Delegating actual byte storage to the shared S3Client integration
- Retrieving stored image URLs by recipe id

This module has no direct database dependency; it works purely with the
upload payload and an in-memory reference map plus the S3 integration.
"""
from __future__ import annotations

import uuid
from typing import Dict, Optional

from fastapi import UploadFile

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class ImageValidationError(Exception):
    """Raised when an uploaded image fails validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _extract_extension(filename: Optional[str]) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


class ImageService:
    """
    Handles validation, storage reference generation, and retrieval of
    recipe images. Storage is delegated to the shared S3Client integration
    when available; falls back to an in-memory registry for local/dev/test
    use, keeping this module self-contained and independently testable.
    """

    def __init__(self, s3_client: Optional[object] = None) -> None:
        # s3_client is expected to conform to app.integrations.s3_client.S3Client's
        # interface: upload_file(file_content: bytes, file_name: str,
        # content_type: str) -> str and get_file_url(file_name: str) -> str.
        # It is optional/injectable to keep this module testable without a
        # real S3 backend and to avoid a hard import-time dependency.
        self._s3_client = s3_client
        self._recipe_image_registry: Dict[str, str] = {}

    def _validate_upload(self, file: UploadFile, content: bytes) -> None:
        """Validate size and content-type/extension of an uploaded image."""
        if len(content) == 0:
            raise ImageValidationError("Uploaded file is empty.")

        if len(content) > MAX_IMAGE_SIZE_BYTES:
            raise ImageValidationError(
                f"Uploaded image exceeds maximum size of "
                f"{MAX_IMAGE_SIZE_BYTES // (1024 * 1024)}MB."
            )

        content_type = (file.content_type or "").lower()
        extension = _extract_extension(file.filename)

        content_type_ok = content_type in ALLOWED_CONTENT_TYPES
        extension_ok = extension in ALLOWED_EXTENSIONS

        if not content_type_ok and not extension_ok:
            raise ImageValidationError(
                "Unsupported image format. Only JPEG and PNG are allowed."
            )

    def upload_image(self, file: UploadFile, recipe_id: str) -> str:
        """
        Validate and store an uploaded image for a given recipe.

        Args:
            file: the FastAPI UploadFile from the multipart request.
            recipe_id: the id of the recipe the image belongs to.

        Returns:
            The stored image's public URL/reference.

        Raises:
            ImageValidationError: if size or format validation fails.
        """
        if not recipe_id or not recipe_id.strip():
            raise ImageValidationError("recipe_id is required to upload an image.")

        content = file.file.read()
        try:
            self._validate_upload(file, content)
        finally:
            # Reset stream position for any downstream consumers.
            try:
                file.file.seek(0)
            except (AttributeError, OSError):
                pass

        extension = _extract_extension(file.filename) or ".jpg"
        storage_key = f"recipes/{recipe_id}/{uuid.uuid4().hex}{extension}"

        content_type = file.content_type or "image/jpeg"

        if self._s3_client is not None:
            url = self._s3_client.upload_file(content, storage_key, content_type)
        else:
            # Local fallback reference when no storage backend is injected.
            url = f"/media/{storage_key}"

        self._recipe_image_registry[recipe_id] = url
        return url

    def get_image_url(self, recipe_id: str) -> Optional[str]:
        """
        Retrieve the stored image URL for a recipe, if one exists.

        Args:
            recipe_id: the id of the recipe.

        Returns:
            The image URL if present, otherwise None.
        """
        if not recipe_id:
            return None

        cached = self._recipe_image_registry.get(recipe_id)
        if cached is not None:
            return cached

        if self._s3_client is not None:
            try:
                return self._s3_client.get_file_url(recipe_id)
            except Exception:
                return None

        return None

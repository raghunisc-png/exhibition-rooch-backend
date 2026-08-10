"""
File storage abstraction.

Supports:

- Local disk storage
- S3-compatible object storage

Used for:

- Product photos
- Generated invoice PDFs

The database stores only the relative storage path/key.

Example:

    photos/abc123.jpg
    invoices/INV-2026-0001.pdf

The public URL is generated separately using `public_url()`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings


settings = get_settings()


# ============================================================
# HELPERS
# ============================================================


def _ext_for(
    filename: str | None,
    default: str = ".bin",
) -> str:
    """
    Extract a safe lowercase file extension.

    Example:

        photo.jpg -> .jpg
        image.PNG -> .png
        None      -> .bin
    """

    if not filename:
        return default

    ext = Path(filename).suffix.lower()

    if not ext:
        return default

    # Keep extension reasonably constrained.
    if len(ext) > 10:
        return default

    return ext


# ============================================================
# LOCAL STORAGE
# ============================================================


class LocalStorage:
    """
    Store files on the local filesystem.
    """

    def __init__(
        self,
        base_dir: str,
    ):
        self.base_dir = Path(
            base_dir
        ).resolve()

        self.base_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------------
    # SAVE BYTES
    # --------------------------------------------------------

    def save_bytes(
        self,
        data: bytes,
        subdir: str,
        filename: str,
    ) -> str:
        """
        Save raw bytes to local storage.

        Returns the relative path stored in the database.
        """

        target_dir = (
            self.base_dir / subdir
        ).resolve()

        # Prevent directory traversal.
        if not str(target_dir).startswith(
            str(self.base_dir)
        ):
            raise ValueError(
                "Invalid storage directory."
            )

        target_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            target_dir / filename
        ).resolve()

        # Prevent filename/path traversal.
        if not str(path).startswith(
            str(target_dir)
        ):
            raise ValueError(
                "Invalid storage filename."
            )

        with open(
            path,
            "wb",
        ) as file:
            file.write(data)

        return (
            f"{subdir}/{filename}"
        )

    # --------------------------------------------------------
    # PUBLIC URL
    # --------------------------------------------------------

    def url_for(
        self,
        relative_path: str,
    ) -> str:
        """
        Convert a stored relative path into
        a publicly accessible URL.
        """

        return (
            f"{settings.PUBLIC_BASE_URL.rstrip('/')}"
            f"/files/{relative_path}"
        )

    # --------------------------------------------------------
    # ABSOLUTE PATH
    # --------------------------------------------------------

    def absolute_path(
        self,
        relative_path: str,
    ) -> Path:
        """
        Convert a stored relative path to
        an absolute filesystem path.

        Used by the PDF generator when it needs
        to load the product photo.
        """

        path = (
            self.base_dir
            / relative_path
        ).resolve()

        # Prevent directory traversal.
        if not str(path).startswith(
            str(self.base_dir)
        ):
            raise ValueError(
                "Invalid storage path."
            )

        return path


# ============================================================
# S3 STORAGE
# ============================================================


class S3Storage:
    """
    S3-compatible object storage.

    boto3 is imported lazily so local deployments
    don't require it unless S3 storage is selected.
    """

    def __init__(self):
        import boto3

        self.client = boto3.client(
            "s3",
            region_name=(
                settings.S3_REGION
                or None
            ),
            aws_access_key_id=(
                settings.S3_ACCESS_KEY_ID
                or None
            ),
            aws_secret_access_key=(
                settings.S3_SECRET_ACCESS_KEY
                or None
            ),
            endpoint_url=(
                settings.S3_ENDPOINT_URL
                or None
            ),
        )

        self.bucket = settings.S3_BUCKET

        if not self.bucket:
            raise ValueError(
                "S3_BUCKET is required when "
                "STORAGE_BACKEND=s3."
            )

    # --------------------------------------------------------
    # SAVE BYTES
    # --------------------------------------------------------

    def save_bytes(
        self,
        data: bytes,
        subdir: str,
        filename: str,
    ) -> str:
        """
        Upload bytes to S3-compatible storage.
        """

        key = (
            f"{subdir}/{filename}"
        )

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
        )

        return key

    # --------------------------------------------------------
    # PUBLIC URL
    # --------------------------------------------------------

    def url_for(
        self,
        relative_path: str,
    ) -> str:
        """
        Generate a public URL for an S3 object.
        """

        # Custom S3-compatible endpoint
        # such as MinIO, Cloudflare R2, etc.
        if settings.S3_ENDPOINT_URL:

            return (
                f"{settings.S3_ENDPOINT_URL.rstrip('/')}"
                f"/{self.bucket}"
                f"/{relative_path}"
            )

        # Standard AWS S3.
        return (
            f"https://{self.bucket}"
            f".s3.{settings.S3_REGION}"
            f".amazonaws.com/"
            f"{relative_path}"
        )


# ============================================================
# STORAGE FACTORY
# ============================================================


def get_storage():
    """
    Return the configured storage backend.
    """

    if settings.STORAGE_BACKEND == "s3":
        return S3Storage()

    return LocalStorage(
        settings.UPLOAD_DIR
    )


# ============================================================
# UPLOAD FILE
# ============================================================


async def save_upload(
    file: UploadFile,
    subdir: str,
) -> str:
    """
    Save a FastAPI UploadFile.

    Used by the online invoice endpoint.

    Returns the relative storage path.
    """

    if not file:
        raise ValueError(
            "File is required."
        )

    data = await file.read()

    if not data:
        raise ValueError(
            "Uploaded file is empty."
        )

    filename = (
        f"{uuid.uuid4().hex}"
        f"{_ext_for(file.filename)}"
    )

    storage = get_storage()

    return storage.save_bytes(
        data,
        subdir,
        filename,
    )


# ============================================================
# SAVE RAW BYTES
# ============================================================


def save_bytes(
    data: bytes,
    subdir: str,
    filename: str,
) -> str:
    """
    Save raw bytes.

    Used primarily by:

    - Offline photo synchronization
    - PDF generation
    """

    if not data:
        raise ValueError(
            "Cannot store empty data."
        )

    return get_storage().save_bytes(
        data,
        subdir,
        filename,
    )


# ============================================================
# PUBLIC URL
# ============================================================


def public_url(
    relative_path: str,
) -> str:
    """
    Convert a stored relative path into
    a public URL.

    Example:

        invoices/INV-2026-0001.pdf

    becomes:

        http://localhost:8000/files/invoices/INV-2026-0001.pdf
    """

    if not relative_path:
        raise ValueError(
            "Storage path is required."
        )

    return get_storage().url_for(
        relative_path
    )
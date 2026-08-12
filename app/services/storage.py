"""
File storage abstraction.

Supports:

- Local disk storage
- S3-compatible object storage

Used for:

- Product photos
- Generated invoice PDFs

The database stores only the relative storage path/key.

Examples:

    photos/abc123.jpg
    invoices/INV-2026-0001.pdf
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.config import get_settings


settings = get_settings()


# ============================================================
# CONSTANTS
# ============================================================

MAX_UPLOAD_BYTES = (
    8 * 1024 * 1024
)

DEFAULT_EXTENSION = ".bin"


# ============================================================
# HELPERS
# ============================================================


def _ext_for(
    filename: str | None,
    default: str = DEFAULT_EXTENSION,
) -> str:
    """
    Extract a safe lowercase file extension.

    Examples:

        photo.jpg -> .jpg
        image.PNG -> .png
        None      -> .bin
    """

    if not filename:
        return default

    ext = Path(
        filename
    ).suffix.lower()

    if not ext:
        return default

    # Prevent unusual / excessively long extensions.
    if len(ext) > 10:
        return default

    # Only allow simple extensions.
    if not ext.startswith("."):
        return default

    if not ext[1:].isalnum():
        return default

    return ext


def _safe_relative_path(
    relative_path: str,
) -> str:
    """
    Validate and normalize a storage-relative path.

    Storage paths always use POSIX-style separators because
    they are also used as S3 object keys.
    """

    if not relative_path:
        raise ValueError(
            "Storage path is required."
        )

    path = PurePosixPath(
        str(relative_path)
        .replace("\\", "/")
    )

    if path.is_absolute():
        raise ValueError(
            "Absolute storage paths are not allowed."
        )

    parts = path.parts

    if not parts:
        raise ValueError(
            "Invalid storage path."
        )

    if any(
        part in {"", ".", ".."}
        for part in parts
    ):
        raise ValueError(
            "Invalid storage path."
        )

    return "/".join(parts)


def _safe_subdir(
    subdir: str,
) -> str:
    """
    Validate a storage subdirectory.
    """

    return _safe_relative_path(
        subdir
    )


def _safe_filename(
    filename: str,
) -> str:
    """
    Validate a storage filename.

    The filename must be a single path component.
    """

    if not filename:
        raise ValueError(
            "Storage filename is required."
        )

    normalized = str(
        filename
    ).replace("\\", "/")

    path = PurePosixPath(
        normalized
    )

    if (
        len(path.parts) != 1
        or path.name != normalized
        or path.name in {
            "",
            ".",
            "..",
        }
    ):
        raise ValueError(
            "Invalid storage filename."
        )

    return path.name


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
    # SAFE PATH
    # --------------------------------------------------------

    def _absolute_storage_path(
        self,
        relative_path: str,
    ) -> Path:
        """
        Resolve a storage-relative path safely.
        """

        safe_relative = (
            _safe_relative_path(
                relative_path
            )
        )

        path = (
            self.base_dir
            / Path(safe_relative)
        ).resolve()

        if not path.is_relative_to(
            self.base_dir
        ):
            raise ValueError(
                "Invalid storage path."
            )

        return path

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

        if not data:
            raise ValueError(
                "Cannot store empty data."
            )

        safe_subdir = (
            _safe_subdir(
                subdir
            )
        )

        safe_filename = (
            _safe_filename(
                filename
            )
        )

        relative_path = (
            f"{safe_subdir}/"
            f"{safe_filename}"
        )

        path = (
            self._absolute_storage_path(
                relative_path
            )
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "wb"
        ) as file:

            file.write(
                data
            )

        return relative_path

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

        safe_relative = (
            _safe_relative_path(
                relative_path
            )
        )

        return (
            f"{settings.PUBLIC_BASE_URL.rstrip('/')}"
            f"/files/"
            f"{safe_relative}"
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
        to load a product photo.
        """

        return (
            self._absolute_storage_path(
                relative_path
            )
        )


# ============================================================
# S3 STORAGE
# ============================================================


class S3Storage:
    """
    S3-compatible object storage.

    boto3 is imported lazily so local deployments do not
    require S3 dependencies unless S3 storage is selected.
    """

    def __init__(self):
        import boto3

        if not settings.S3_BUCKET:
            raise ValueError(
                "S3_BUCKET is required when "
                "STORAGE_BACKEND=s3."
            )

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

        self.bucket = (
            settings.S3_BUCKET
        )

    # --------------------------------------------------------
    # SAVE BYTES
    # --------------------------------------------------------

    def save_bytes(
        self,
        data: bytes,
        subdir: str,
        filename: str,
        content_type: str | None = None,
    ) -> str:
        """
        Upload bytes to S3-compatible storage.
        """

        if not data:
            raise ValueError(
                "Cannot store empty data."
            )

        safe_subdir = (
            _safe_subdir(
                subdir
            )
        )

        safe_filename = (
            _safe_filename(
                filename
            )
        )

        key = (
            f"{safe_subdir}/"
            f"{safe_filename}"
        )

        put_kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
        }

        if content_type:
            put_kwargs[
                "ContentType"
            ] = content_type

        self.client.put_object(
            **put_kwargs
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

        For S3-compatible providers, S3_ENDPOINT_URL is used
        when configured.

        IMPORTANT:
        The bucket/object must actually be publicly accessible
        for this URL to work.
        """

        safe_relative = (
            _safe_relative_path(
                relative_path
            )
        )

        if settings.S3_ENDPOINT_URL:

            return (
                f"{settings.S3_ENDPOINT_URL.rstrip('/')}"
                f"/{self.bucket}"
                f"/{safe_relative}"
            )

        if not settings.S3_REGION:
            raise ValueError(
                "S3_REGION is required for "
                "standard AWS S3 public URLs."
            )

        return (
            f"https://{self.bucket}"
            f".s3.{settings.S3_REGION}"
            f".amazonaws.com/"
            f"{safe_relative}"
        )

    # --------------------------------------------------------
    # ABSOLUTE PATH
    # --------------------------------------------------------

    def absolute_path(
        self,
        relative_path: str,
    ) -> Path:
        """
        S3 objects do not have a local filesystem path.

        The PDF generator should only call this method when
        using local storage.
        """

        raise RuntimeError(
            "absolute_path() is not available "
            "for S3 storage."
        )


# ============================================================
# STORAGE FACTORY
# ============================================================


@lru_cache(maxsize=1)
def get_storage():
    """
    Return the configured storage backend.

    The storage instance is cached so an S3 client or local
    storage object is not recreated on every request.
    """

    if (
        settings.STORAGE_BACKEND
        == "s3"
    ):

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

    Maximum upload size:
        8 MB
    """

    if not file:
        raise ValueError(
            "File is required."
        )

    # --------------------------------------------------------
    # Read upload
    # --------------------------------------------------------

    data = await file.read()

    if not data:
        raise ValueError(
            "Uploaded file is empty."
        )

    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            "Uploaded file exceeds the 8MB limit."
        )

    # --------------------------------------------------------
    # Generate safe filename
    # --------------------------------------------------------

    filename = (
        f"{uuid.uuid4().hex}"
        f"{_ext_for(file.filename)}"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    storage = get_storage()

    content_type = (
        getattr(
            file,
            "content_type",
            None,
        )
        or None
    )

    if isinstance(
        storage,
        S3Storage,
    ):

        return storage.save_bytes(
            data,
            subdir,
            filename,
            content_type=content_type,
        )

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

        http://localhost:8000/files/
        invoices/INV-2026-0001.pdf
    """

    safe_relative = (
        _safe_relative_path(
            relative_path
        )
    )

    return get_storage().url_for(
        safe_relative
    )
"""
File storage abstraction. Supports local disk (default, good enough for a
single-server deployment behind a reverse proxy) and S3-compatible object
storage (recommended once you run more than one backend instance).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()


def _ext_for(filename: str | None, default: str = ".bin") -> str:
    if not filename:
        return default
    ext = Path(filename).suffix.lower()
    return ext if ext else default


class LocalStorage:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, data: bytes, subdir: str, filename: str) -> str:
        target_dir = self.base_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        with open(path, "wb") as f:
            f.write(data)
        # Return a relative path (relative to base_dir) which is what we
        # store in the DB; url_for() below turns it into a public URL.
        return f"{subdir}/{filename}"

    def url_for(self, relative_path: str) -> str:
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/files/{relative_path}"

    def absolute_path(self, relative_path: str) -> Path:
        return self.base_dir / relative_path


class S3Storage:
    def __init__(self):
        import boto3  # imported lazily so local-only deployments don't need boto3

        self.client = boto3.client(
            "s3",
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
        )
        self.bucket = settings.S3_BUCKET

    def save_bytes(self, data: bytes, subdir: str, filename: str) -> str:
        key = f"{subdir}/{filename}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def url_for(self, relative_path: str) -> str:
        if settings.S3_ENDPOINT_URL:
            return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{self.bucket}/{relative_path}"
        return f"https://{self.bucket}.s3.{settings.S3_REGION}.amazonaws.com/{relative_path}"


def get_storage():
    if settings.STORAGE_BACKEND == "s3":
        return S3Storage()
    return LocalStorage(settings.UPLOAD_DIR)


async def save_upload(file: UploadFile, subdir: str) -> str:
    """Save an UploadFile and return the stored relative path."""
    storage = get_storage()
    data = await file.read()
    filename = f"{uuid.uuid4().hex}{_ext_for(file.filename)}"
    return storage.save_bytes(data, subdir, filename)


def save_bytes(data: bytes, subdir: str, filename: str) -> str:
    return get_storage().save_bytes(data, subdir, filename)


def public_url(relative_path: str) -> str:
    return get_storage().url_for(relative_path)

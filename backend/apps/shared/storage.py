"""File storage seam (playbook 4.6, DECISIONS D-11). Binary artefacts never live in the
database. `get_storage()` returns the backend for the environment: local for dev and
tests, a private S3-compatible bucket when deployed. Keys are deterministic (tenant id
plus row id), a failed write raises inside the transaction that creates the row, and
nothing is public: downloads stream through permission-checked endpoints.

The production-safety block refuses STORAGE_BACKEND=local when deployed; `get_storage()`
refuses it again here so a settings override in a shell cannot slip past."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def object_key(tenant_id: uuid.UUID | None, row_id: uuid.UUID, filename: str) -> str:
    """Deterministic and free of user-chosen path segments: the filename is reduced to
    its suffix so a name can never traverse."""
    suffix = Path(filename).suffix.lower()[:16]
    zone = str(tenant_id) if tenant_id else "library"
    return f"{zone}/{row_id}{suffix}"


class StorageBackend(ABC):
    name: str

    @abstractmethod
    def write(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(StorageBackend):
    """Dev and tests only. Files under MEDIA_ROOT; refused when deployed."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key escapes the storage root")
        return path

    def write(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()


class S3Storage(StorageBackend):
    """A private S3-compatible bucket through boto3. Objects are never public and are
    never linked directly (D-11)."""

    name = "s3"

    def __init__(self) -> None:
        import boto3

        if not settings.STORAGE_S3_BUCKET:
            raise ImproperlyConfigured("STORAGE_S3_BUCKET is required for STORAGE_BACKEND=s3")
        self.bucket = settings.STORAGE_S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_S3_ENDPOINT_URL or None,
            region_name=settings.STORAGE_S3_REGION,
            aws_access_key_id=settings.STORAGE_S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.STORAGE_S3_SECRET_ACCESS_KEY or None,
        )

    def write(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> StorageBackend:
    backend = settings.STORAGE_BACKEND
    if backend == "local":
        if settings.IS_DEPLOYED_ENVIRONMENT:
            raise ImproperlyConfigured(
                "Refusing the local storage backend on a deployed environment: a container's "
                "disk is ephemeral and evidence written there is lost (playbook 4.6)."
            )
        return LocalStorage(settings.MEDIA_ROOT)
    if backend == "s3":
        return S3Storage()
    raise ImproperlyConfigured(f"STORAGE_BACKEND={backend!r} is not one of local, s3")

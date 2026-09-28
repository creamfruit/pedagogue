from __future__ import annotations

import hashlib
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional

from app.core.config import settings


class StorageError(RuntimeError):
    pass


class FileTooLarge(StorageError):
    pass


class UnsupportedMediaType(StorageError):
    pass


class Storage(ABC):
    def __init__(self, max_bytes: Optional[int] = None) -> None:
        self.max_bytes = max_bytes or settings.max_upload_bytes

    @abstractmethod
    def save(self, stream: BinaryIO, key: str) -> int: ...

    @abstractmethod
    def open(self, key: str) -> BinaryIO: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def url(self, key: str) -> str: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int: ...

    def delete_user_files(self, user_id: uuid.UUID) -> int:
        return sum(self.delete_prefix(f"{kind}/{user_id}/") for kind in USER_FILE_KINDS)

    def build_key(self, user_id: uuid.UUID, kind: str, filename: str) -> str:
        suffix = Path(filename).suffix.lower()[:10]
        token = uuid.uuid4().hex
        return f"{kind}/{user_id}/{token}{suffix}"

    def guard_size(self, size: int) -> None:
        if size > self.max_bytes:
            raise FileTooLarge(f"file exceeds {self.max_bytes // (1024 * 1024)} MB limit")


class LocalStorage(Storage):
    def __init__(self, root: str = "storage", max_bytes: Optional[int] = None) -> None:
        super().__init__(max_bytes)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root)):
            raise StorageError("key escapes storage root")
        return target

    def save(self, stream: BinaryIO, key: str) -> int:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        digest = hashlib.sha256()
        with target.open("wb") as handle:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > self.max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise FileTooLarge(f"file exceeds {self.max_bytes // (1024 * 1024)} MB limit")
                digest.update(chunk)
                handle.write(chunk)
        return written

    def open(self, key: str) -> BinaryIO:
        target = self.path_for(key)
        if not target.exists():
            raise StorageError(f"missing object {key}")
        return target.open("rb")

    def delete(self, key: str) -> bool:
        target = self.path_for(key)
        if target.exists():
            target.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self.path_for(key).exists()

    def delete_prefix(self, prefix: str) -> int:
        target = self.path_for(prefix)
        if target == self.root or not target.is_dir():
            return 0
        removed = sum(1 for path in target.rglob("*") if path.is_file())
        shutil.rmtree(target, ignore_errors=True)
        return removed

    def url(self, key: str) -> str:
        return f"file://{self.path_for(key)}"

    def purge(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


class S3Storage(Storage):
    def __init__(self, bucket: Optional[str] = None, max_bytes: Optional[int] = None) -> None:
        super().__init__(max_bytes)
        self.bucket = bucket or settings.storage_bucket
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.storage_endpoint,
                aws_access_key_id=settings.storage_access_key,
                aws_secret_access_key=settings.storage_secret_key,
            )
        return self._client

    def save(self, stream: BinaryIO, key: str) -> int:
        body = stream.read()
        self.guard_size(len(body))
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body)
        return len(body)

    def open(self, key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"]

    def delete(self, key: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete_prefix(self, prefix: str) -> int:
        removed = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            for start in range(0, len(objects), 1000):
                batch = objects[start : start + 1000]
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
                removed += len(batch)
        return removed

    def url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )


USER_FILE_KINDS = ("scores", "recordings", "musicxml", "midi")

PDF_TYPES = {"application/pdf"}
AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/mp4",
    "audio/aac",
    "audio/m4a",
    "audio/x-m4a",
}


def ensure_media_type(content_type: Optional[str], allowed: set[str], label: str) -> str:
    normalised = (content_type or "").split(";")[0].strip().lower()
    if normalised not in allowed:
        raise UnsupportedMediaType(f"expected {label}, received {content_type or 'unknown'}")
    return normalised


def get_storage() -> Storage:
    if settings.storage_endpoint:
        return S3Storage()
    return LocalStorage()


storage = get_storage()

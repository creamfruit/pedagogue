from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings

logger = logging.getLogger("piano.backup")

DUMP_SUFFIX = ".dump"


@dataclass(frozen=True)
class Backup:
    key: str
    size: int
    modified: datetime


def plain_dsn(url: str) -> str:
    scheme, separator, rest = url.partition("://")
    if separator and scheme.startswith("postgresql+"):
        return f"postgresql://{rest}"
    return url


def dump_command(dsn: str, target: Path) -> list[str]:
    return [
        settings.backup_pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--compress=6",
        f"--file={target}",
        f"--dbname={plain_dsn(dsn)}",
    ]


def backup_key(now: datetime) -> str:
    return f"{settings.backup_prefix}pedagogue-{now.strftime('%Y%m%dT%H%M%SZ')}{DUMP_SUFFIX}"


def expired(backups: list[Backup], now: datetime) -> list[Backup]:
    newest_first = sorted(backups, key=lambda backup: backup.modified, reverse=True)
    cutoff = now - timedelta(days=settings.backup_retention_days)
    return [backup for backup in newest_first[settings.backup_keep_min :] if backup.modified < cutoff]


class BucketStore:
    def __init__(self, client=None, bucket: Optional[str] = None) -> None:
        self.bucket = bucket or settings.backup_bucket or settings.storage_bucket
        self._client = client

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

    def upload(self, path: Path, key: str) -> None:
        self.client.upload_file(str(path), self.bucket, key)

    def list(self) -> list[Backup]:
        found = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=settings.backup_prefix):
            for item in page.get("Contents", []):
                if item["Key"].endswith(DUMP_SUFFIX):
                    found.append(Backup(item["Key"], int(item.get("Size", 0)), item["LastModified"]))
        return found

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def download(self, key: str, path: Path) -> None:
        self.client.download_file(self.bucket, key, str(path))


class FolderStore:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = Path(root or settings.backup_local_dir or Path.home() / ".pedagogue" / "backups")
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / Path(key).name

    def upload(self, path: Path, key: str) -> None:
        shutil.copyfile(path, self.path_for(key))

    def list(self) -> list[Backup]:
        return [
            Backup(f"{settings.backup_prefix}{path.name}", path.stat().st_size, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
            for path in self.root.glob(f"*{DUMP_SUFFIX}")
        ]

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)

    def download(self, key: str, path: Path) -> None:
        shutil.copyfile(self.path_for(key), path)


def default_store():
    return BucketStore() if settings.storage_endpoint else FolderStore()


def run_backup(store=None, runner: Callable = subprocess.run, now: Optional[datetime] = None) -> dict:
    store = store or default_store()
    now = now or datetime.now(timezone.utc)
    key = backup_key(now)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / Path(key).name
        runner(dump_command(settings.sync_dsn, target), check=True)
        size = target.stat().st_size
        if size == 0:
            raise RuntimeError("pg_dump wrote an empty file")
        store.upload(target, key)
    removed = []
    for backup in expired(store.list(), now):
        store.delete(backup.key)
        removed.append(backup.key)
    logger.info("backup %s uploaded (%s bytes), %s expired backups removed", key, size, len(removed))
    return {"key": key, "size": size, "removed": removed}


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.ops.backup", description="Back up the Pedagogue database.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="dump the database and upload it (the default)")
    commands.add_parser("list", help="list stored backups, newest first")
    fetch = commands.add_parser("download", help="download one backup")
    fetch.add_argument("key")
    fetch.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    from app.core.monitoring import init_sentry

    init_sentry("backup")
    store = default_store()
    if args.command == "list":
        for backup in sorted(store.list(), key=lambda item: item.modified, reverse=True):
            print(f"{backup.modified.isoformat()}  {backup.size:>12}  {backup.key}")
        return 0
    if args.command == "download":
        store.download(args.key, args.path)
        print(f"saved {args.key} to {args.path}")
        return 0
    result = run_backup(store)
    print(f"uploaded {result['key']} ({result['size']} bytes); removed {len(result['removed'])} expired")
    return 0


if __name__ == "__main__":
    sys.exit(main())

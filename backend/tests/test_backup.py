import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from app.core.config import settings
from app.ops import backup
from app.ops.backup import Backup, BucketStore, FolderStore, dump_command, expired, plain_dsn, run_backup

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)


def fake_pg_dump(body=b"PGDMP fake dump"):
    calls = []

    def runner(command, check):
        assert check is True
        calls.append(command)
        target = next(part.split("=", 1)[1] for part in command if part.startswith("--file="))
        Path(target).write_bytes(body)

    runner.calls = calls
    return runner


def test_dump_uses_a_plain_postgres_url_and_the_custom_format(tmp_path):
    assert plain_dsn("postgresql+psycopg://piano:secret@db:5432/piano") == "postgresql://piano:secret@db:5432/piano"
    assert plain_dsn("postgresql://u@h/d") == "postgresql://u@h/d"
    command = dump_command("postgresql+psycopg://piano:secret@db:5432/piano", tmp_path / "x.dump")
    assert command[0] == "pg_dump"
    assert "--format=custom" in command and "--no-owner" in command
    assert "--dbname=postgresql://piano:secret@db:5432/piano" in command


def test_expiry_keeps_the_newest_backups_whatever_their_age(monkeypatch):
    monkeypatch.setattr(settings, "backup_retention_days", 30)
    monkeypatch.setattr(settings, "backup_keep_min", 3)
    old = [Backup(f"backups/{day}.dump", 1, NOW - timedelta(days=day)) for day in (40, 50, 60, 70, 80)]
    recent = [Backup(f"backups/{day}.dump", 1, NOW - timedelta(days=day)) for day in (1, 2)]
    removed = {item.key for item in expired(old + recent, NOW)}
    assert removed == {"backups/50.dump", "backups/60.dump", "backups/70.dump", "backups/80.dump"}
    assert expired(old[:3], NOW) == []


def test_a_nightly_run_uploads_one_dump_and_prunes_old_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_keep_min", 1)
    store = FolderStore(str(tmp_path))
    stale = tmp_path / "pedagogue-20260801T030000Z.dump"
    stale.write_bytes(b"old")
    old_time = (NOW - timedelta(days=90)).timestamp()
    os.utime(stale, (old_time, old_time))
    runner = fake_pg_dump()
    result = run_backup(store, runner=runner, now=NOW)
    assert result["key"] == "backups/pedagogue-20261019T030000Z.dump"
    assert (tmp_path / "pedagogue-20261019T030000Z.dump").read_bytes() == b"PGDMP fake dump"
    assert result["removed"] == ["backups/pedagogue-20260801T030000Z.dump"]
    assert not stale.exists()
    assert len(runner.calls) == 1


def test_an_empty_dump_is_an_error_and_nothing_is_uploaded(tmp_path):
    store = FolderStore(str(tmp_path))
    with pytest.raises(RuntimeError):
        run_backup(store, runner=fake_pg_dump(b""), now=NOW)
    assert list(tmp_path.iterdir()) == []


def test_pg_dump_failures_stop_the_run(tmp_path):
    import subprocess

    def failing(command, check):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        run_backup(FolderStore(str(tmp_path)), runner=failing, now=NOW)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key):
        self.objects[(bucket, key)] = (Path(path).read_bytes(), NOW)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key))

    def get_paginator(self, name):
        store = self

        class Pages:
            def paginate(self, Bucket, Prefix):
                yield {
                    "Contents": [
                        {"Key": key, "Size": len(body), "LastModified": modified}
                        for (bucket, key), (body, modified) in store.objects.items()
                        if bucket == Bucket and key.startswith(Prefix)
                    ]
                }

        return Pages()


def test_backups_go_to_their_own_bucket_when_one_is_set(monkeypatch):
    monkeypatch.setattr(settings, "backup_bucket", "pedagogue-backups")
    client = FakeS3()
    client.objects[("pedagogue-backups", "backups/pedagogue-20260101T030000Z.dump")] = (b"old", NOW - timedelta(days=200))
    client.objects[("pedagogue-uploads", "scores/u/a.pdf")] = (b"%PDF", NOW - timedelta(days=200))
    monkeypatch.setattr(settings, "backup_keep_min", 1)
    result = run_backup(BucketStore(client=client), runner=fake_pg_dump(), now=NOW)
    assert ("pedagogue-backups", result["key"]) in client.objects
    assert ("pedagogue-backups", "backups/pedagogue-20260101T030000Z.dump") not in client.objects
    assert ("pedagogue-uploads", "scores/u/a.pdf") in client.objects


def test_the_blueprint_runs_the_backup_every_night():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    cron = next(service for service in blueprint["services"] if service["name"] == "pedagogue-backup")
    assert cron["type"] == "cron"
    minute, hour, day, month, weekday = cron["schedule"].split()
    assert (day, month, weekday) == ("*", "*", "*") and minute.isdigit() and hour.isdigit()
    assert cron["dockerCommand"] == "scripts/backup.sh"
    env = {item["key"]: item for item in cron["envVars"]}
    assert env["DATABASE_URL"]["fromDatabase"]["name"] == "pedagogue-db"
    for key in ("STORAGE_ENDPOINT", "STORAGE_ACCESS_KEY", "STORAGE_SECRET_KEY", "BACKUP_BUCKET"):
        assert key in env
    script = (ROOT / "backend" / "scripts" / "backup.sh").read_text(encoding="utf-8")
    assert "python -m app.ops.backup run" in script


def test_the_image_ships_a_pg_dump_new_enough_for_the_database():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    server = int(blueprint["databases"][0]["postgresMajorVersion"])
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    client = int(re.search(r"postgresql-client-(\d+)", dockerfile).group(1))
    assert client >= server


def test_the_command_line_lists_backups(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "storage_endpoint", None)
    monkeypatch.setattr(settings, "backup_local_dir", str(tmp_path))
    (tmp_path / "pedagogue-20261018T030000Z.dump").write_bytes(b"dump")
    assert backup.main(["list"]) == 0
    assert "backups/pedagogue-20261018T030000Z.dump" in capsys.readouterr().out

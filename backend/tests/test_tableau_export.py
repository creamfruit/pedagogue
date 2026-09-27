import os
import shutil
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services.tableau_export import Table, build_file, plain

hyper = pytest.importorskip("tableauhyperapi")
TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


def read_back(path, workdir):
    with hyper.HyperProcess(
        telemetry=hyper.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_dir": workdir}
    ) as process:
        with hyper.Connection(process.endpoint, path) as connection:
            return {
                str(name.name.unescaped): connection.execute_list_query(f"SELECT * FROM {name}")
                for name in connection.catalog.get_table_names("Extract")
            }


def test_plain_flattens_decimals_and_enums():
    from app.models.models import RepertoireStatus

    assert plain(Decimal("7.20")) == 7.2
    assert plain(RepertoireStatus.LEARNING) == "learning"
    assert plain(None) is None


def test_build_file_writes_every_type_and_nulls():
    when = datetime(2026, 9, 27, 12, 30, tzinfo=timezone.utc)
    tables = [
        Table(
            "sample",
            [("name", "text"), ("count", "int"), ("score", "double"), ("flag", "bool"), ("day", "date"), ("at", "timestamp")],
            [["a", 3, 81.5, True, date(2026, 9, 27), when], [None, None, None, None, None, None]],
        ),
        Table("empty", [("name", "text")]),
    ]
    path, workdir = build_file(tables)
    try:
        rows = read_back(path, workdir)
        assert set(rows) == {"sample", "empty"}
        assert rows["empty"] == []
        first = rows["sample"][0]
        assert first[:4] == ["a", 3, 81.5, True]
        assert str(first[4]) == "2026-09-27"
        assert rows["sample"][1] == [None] * 6
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    assert not os.path.exists(workdir)


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
async def test_collect_exports_a_users_history():
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import LedgerEntry, LedgerReason, Piece, RepertoireEntry, User, Wallet
    from app.services.economy import EconomyService
    from app.services.tableau_export import TableauExportService

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(email="export-a@example.com", password_hash="x", display_name="Export")
        session.add(user)
        await session.commit()
        user_id = user.id
        try:
            piece_id = (await session.execute(select(Piece.id).where(Piece.is_user_created.is_(False)).limit(1))).scalar_one()
            session.add(RepertoireEntry(user_id=user_id, piece_id=piece_id))
            economy = EconomyService(session)
            await economy.award(user, 50, 30, LedgerReason.ADJUSTMENT, detail="test")
            await economy.award(user, 20, 10, LedgerReason.ADJUSTMENT, detail="test")
            await session.flush()
            tables = {table.name: table for table in await TableauExportService(session).collect(user)}
            assert set(tables) == {"repertoire", "practice_sessions", "practice_items", "submissions", "technique_mastery", "wallet_history"}
            assert len(tables["repertoire"].rows) == 1
            history = tables["wallet_history"].rows
            assert [row[-2:] for row in history] == [[50, 30], [70, 40]]
        finally:
            await session.rollback()
            await session.execute(delete(LedgerEntry).where(LedgerEntry.user_id == user_id))
            await session.execute(delete(RepertoireEntry).where(RepertoireEntry.user_id == user_id))
            await session.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    await engine.dispose()

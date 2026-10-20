import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.models import (
    KeyboardAttempt,
    LedgerEntry,
    LedgerReason,
    PracticeMode,
    PracticeSession,
    RepertoireEntry,
    SessionItem,
    Wallet,
)
from app.services.keyboard import counted_seconds, review_due_at
from app.services.keyboard_scoring import PlayedNote, refreshed_practice_time
from app.services.streaks import StreakService
from tests.test_keyboard_api import client, needs_db, passage, perform, world  # noqa: F401

ATTEMPTS = "/api/v1/keyboard/entries/{}/attempts"


def eighths(count=16, tempo=100, jitter=None):
    step = 60000.0 / tempo / 2
    return [{"t": i * step + (jitter(i) if jitter else 0.0), "midi": 60 + i % 5} for i in range(count)]


async def free(http, entry, notes, tempo=100, duration=20, count_in=4):
    response = await http.post(ATTEMPTS.format(entry), json={"mode": "free", "tempo_bpm": tempo, "count_in_beats": count_in, "duration_sec": duration, "notes": notes})
    assert response.status_code == 201, response.text
    return response.json()


async def scored_clean(http, entry, tempo=80, start=1, end=3, duration=20):
    notes = (await passage(http, entry, start, end))["notes"]
    body = {"mode": "scored", "start_bar": start, "end_bar": end, "tempo_bpm": tempo, "duration_sec": duration, "notes": perform(notes, tempo)}
    response = await http.post(ATTEMPTS.format(entry), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_counted_time_cannot_exceed_what_was_played():
    notes = [PlayedNote(0, 60), PlayedNote(8000, 62)]
    assert counted_seconds(notes, 3000, 4) == 22.0
    assert counted_seconds(notes, 15, 4) == 15.0
    assert counted_seconds([], 600, 4) == 0.0
    assert counted_seconds(notes, -5, 4) == 0.0


def test_review_comes_later_for_easier_pieces_and_the_clock_starts_at_the_last_practice():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    easy = review_due_at(start, 20) - start
    hard = review_due_at(start, 90) - start
    assert hard < easy
    assert timedelta(days=4) < hard and easy < timedelta(days=25)
    assert review_due_at(start + timedelta(days=3), 50) - review_due_at(start, 50) == timedelta(days=3)


def test_a_poor_run_leaves_less_extra_time_than_a_good_one():
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    before = now - timedelta(days=10)
    assert review_due_at(refreshed_practice_time(before, now, 40), 50) < review_due_at(refreshed_practice_time(before, now, 90), 50)


@needs_db
async def test_runs_become_a_session_whose_close_pays_xp_and_a_streak_day(world):
    sparse = [{"t": 0, "midi": 60}, {"t": 150000, "midi": 62}, {"t": 300000, "midi": 64}]
    async with client() as http:
        data = await free(http, world.ids.bare, sparse, tempo=60, duration=330)
        assert data["duration_sec"] == 314.0
        assert data["session_id"] and data["session_minutes"] == 6
        closed = await http.post(f"/api/v1/practice/sessions/{data['session_id']}/close", json={})
        assert closed.status_code == 200
    async with world.factory() as session:
        practice = (await session.execute(select(PracticeSession).where(PracticeSession.user_id == world.ids.user))).scalars().all()
        assert [item.mode for item in practice] == [PracticeMode.KEYBOARD] and practice[0].ended_at is not None
        items = (await session.execute(select(SessionItem).where(SessionItem.session_id == practice[0].id))).scalars().all()
        assert [(item.repertoire_entry_id, item.minutes) for item in items] == [(world.ids.bare, 6)]
        wallet = await session.get(Wallet, world.ids.user)
        assert wallet.xp >= 12
        reasons = set((await session.execute(select(LedgerEntry.reason).where(LedgerEntry.user_id == world.ids.user))).scalars().all())
        assert {LedgerReason.PRACTICE_SESSION, LedgerReason.STREAK_BONUS} <= reasons
        from app.models.models import User

        user = await session.get(User, world.ids.user)
        assert (await StreakService(session).stats(user)).current == 1


@needs_db
async def test_a_claimed_duration_is_capped_by_the_notes_actually_played(world):
    async with client() as http:
        data = await free(http, world.ids.bare, eighths(), tempo=100, duration=3000)
    assert data["duration_sec"] < 30
    assert data["session_minutes"] == 1


@needs_db
async def test_attempts_join_the_session_already_open_and_add_to_the_same_item(world):
    async with world.factory() as session:
        session.add(PracticeSession(user_id=world.ids.user, mode=PracticeMode.FREE))
        await session.commit()
    async with client() as http:
        first = await free(http, world.ids.bare, eighths())
        second = await free(http, world.ids.bare, eighths())
        assert first["session_id"] == second["session_id"]
    async with world.factory() as session:
        sessions = (await session.execute(select(PracticeSession).where(PracticeSession.user_id == world.ids.user))).scalars().all()
        assert len(sessions) == 1 and sessions[0].mode == PracticeMode.FREE
        items = (await session.execute(select(SessionItem).where(SessionItem.session_id == sessions[0].id))).scalars().all()
        assert len(items) == 1
        attempts = (await session.execute(select(func.count()).select_from(KeyboardAttempt).where(KeyboardAttempt.session_id == sessions[0].id))).scalar_one()
        assert attempts == 2


@needs_db
async def test_an_attempt_with_no_notes_starts_no_session_and_counts_no_time(world):
    async with client() as http:
        data = await free(http, world.ids.bare, [], duration=600)
    assert data["session_id"] is None and data["duration_sec"] == 0
    async with world.factory() as session:
        found = (await session.execute(select(func.count()).select_from(PracticeSession).where(PracticeSession.user_id == world.ids.user))).scalar_one()
        assert found == 0


async def set_last_practised(world, days):
    async with world.factory() as session:
        entry = await session.get(RepertoireEntry, world.ids.bare)
        entry.last_practiced_at = datetime.now(timezone.utc) - timedelta(days=days)
        await session.commit()


async def last_practised(world):
    async with world.factory() as session:
        return (await session.get(RepertoireEntry, world.ids.bare)).last_practiced_at


@needs_db
async def test_a_good_run_resets_the_review_clock_and_a_poor_one_only_halfway(world):
    rng = random.Random(3)
    async with client() as http:
        await set_last_practised(world, 10)
        good = await free(http, world.ids.bare, eighths())
        stamp = await last_practised(world)
        assert datetime.now(timezone.utc) - stamp < timedelta(minutes=2)
        await set_last_practised(world, 10)
        poor = await free(http, world.ids.bare, eighths(jitter=lambda i: rng.uniform(-100, 100)))
        halfway = await last_practised(world)
        assert poor["overall"] < 60
        assert timedelta(days=4.9) < datetime.now(timezone.utc) - halfway < timedelta(days=5.1)
        assert datetime.fromisoformat(poor["next_review_at"]) < datetime.fromisoformat(good["next_review_at"])


@needs_db
async def test_clearing_a_tempo_rung_pays_once(world):
    async with client() as http:
        runs = [await scored_clean(http, world.ids.entry) for _ in range(3)]
    assert [run["xp_awarded"] for run in runs] == [0, 15, 0]
    assert [run["ladder"]["raised"] for run in runs] == [False, True, True]
    async with world.factory() as session:
        paid = (await session.execute(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.user_id == world.ids.user, LedgerEntry.ref_type == "keyboard_rung"))).scalar_one()
        assert paid == 1
        assert (await session.get(Wallet, world.ids.user)).xp == 15


@needs_db
async def test_a_clean_run_of_the_whole_piece_sets_the_current_tempo_but_a_passage_does_not(world):
    async with client() as http:
        await scored_clean(http, world.ids.entry, tempo=120, start=1, end=3)
        async with world.factory() as session:
            assert (await session.get(RepertoireEntry, world.ids.entry)).current_tempo_bpm is None
        await scored_clean(http, world.ids.entry, tempo=70, start=1, end=12)
        await scored_clean(http, world.ids.entry, tempo=60, start=1, end=12)
    async with world.factory() as session:
        assert (await session.get(RepertoireEntry, world.ids.entry)).current_tempo_bpm == 70


@needs_db
async def test_the_heat_endpoint_averages_the_last_runs_per_bar(world):
    async with client() as http:
        notes = (await passage(http, world.ids.entry, 1, 3))["notes"]
        bar_two = [index for index, note in enumerate(notes) if note[2] == 2][1]
        await scored_clean(http, world.ids.entry)
        slip = {"mode": "scored", "start_bar": 1, "end_bar": 3, "tempo_bpm": 80, "duration_sec": 20, "notes": perform(notes, 80, replace={bar_two: 90})}
        assert (await http.post(ATTEMPTS.format(world.ids.entry), json=slip)).status_code == 201
        heat = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 1, "end_bar": 3})).json()
        assert heat["attempts"] == 2
        by_bar = {item["bar"]: item for item in heat["bars"]}
        assert by_bar[1]["accuracy"] == 1.0 and by_bar[3]["accuracy"] == 1.0
        assert by_bar[2]["accuracy"] < 1.0 and by_bar[2]["wrong"] == 1 and by_bar[2]["attempts"] == 2
        outside = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 8, "end_bar": 12})).json()
        assert outside["attempts"] == 0 and outside["bars"] == []
        backwards = await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 5, "end_bar": 2})
        assert backwards.status_code == 422


@needs_db
async def test_recent_attempts_come_back_newest_first_with_their_bars(world):
    async with client() as http:
        await scored_clean(http, world.ids.entry, tempo=80)
        await scored_clean(http, world.ids.entry, tempo=84)
        recent = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", params={"limit": 5})).json()
        assert [item["tempo_bpm"] for item in recent] == [84, 80]
        assert [bar["bar"] for bar in recent[0]["bars"]] == [1, 2, 3]
        assert recent[0]["note_checking"] is True and recent[0]["session_id"]
        world.current.id = world.ids.other
        assert (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts")).status_code == 404
        assert (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 1, "end_bar": 2})).status_code == 404

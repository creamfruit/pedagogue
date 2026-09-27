import os
from datetime import date

import pytest
from sqlalchemy import delete, select

from app.services.leaderboard import practice_week_board, rank_rows, roulette_board
from app.services.roulette import build_quiz, generate_snippet, score_attempt

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


def test_board_keys():
    assert practice_week_board(date(2026, 9, 27)) == "practice-week:2026-W39"
    assert roulette_board(date(2026, 9, 27)) == "roulette:2026-09-27"


def test_rank_rows_shares_ranks_on_ties():
    rows = rank_rows([{"name": "b", "score": 50.0}, {"name": "a", "score": 90.0}, {"name": "c", "score": 50.0}])
    assert [(row["name"], row["rank"]) for row in rows] == [("a", 1), ("b", 2), ("c", 2)]


def test_snippet_is_identical_for_everyone_on_a_day():
    first, second = generate_snippet(date(2026, 9, 27)), generate_snippet(date(2026, 9, 27))
    assert first["notation"] == second["notation"] and first["quiz"] == second["quiz"]
    assert generate_snippet(date(2026, 9, 28))["notation"] != first["notation"]


def test_quiz_asks_one_note_per_bar_with_the_answer_among_four_options():
    snippet = generate_snippet(date(2026, 10, 3))
    assert len(snippet["quiz"]) == len(snippet["notation"]["measures"])
    for question in snippet["quiz"]:
        assert question["answer"] in question["options"]
        assert len(set(question["options"])) == 4


def test_chords_ask_for_the_top_note():
    notation = {"measures": [{"notes": [{"pitches": ["E4", "C5"], "duration": "q"}]}]}
    import random

    assert build_quiz(notation, random.Random(1))[0]["answer"] == "C"


def test_scoring_rewards_accuracy_then_speed():
    quiz = [{"answer": "C"}] * 8
    perfect_fast = score_attempt(quiz, ["C"] * 8, 30)
    perfect_slow = score_attempt(quiz, ["C"] * 8, 200)
    sloppy_fast = score_attempt(quiz, ["C"] * 3 + ["D"] * 5, 5)
    assert perfect_fast["score"] == 800 + 60 * 2
    assert perfect_slow["score"] == 800
    assert sloppy_fast["speed_bonus"] == 0 and sloppy_fast["score"] == 300


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
async def test_friends_opt_in_and_single_roulette_attempt():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Friendship, LeaderboardEntry, RouletteAttempt, User
    from app.services.leaderboard import FriendService, LeaderboardService
    from app.services.roulette import RouletteService

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    emails = ["lb-a@example.com", "lb-b@example.com", "lb-c@example.com"]
    async with factory() as session:
        users = [User(email=email, password_hash="x", display_name=email[:4]) for email in emails]
        session.add_all(users)
        await session.commit()
        a, b, c = users
        try:
            friends = FriendService(session)
            await friends.request(a, b.email)
            await friends.request(a, "nobody@example.com")
            incoming = (await friends.overview(b))["incoming"]
            assert len(incoming) == 1
            await friends.respond(b, incoming[0]["id"], True)
            assert await friends.friend_ids(a) == {b.id}

            board = "test-board"
            service = LeaderboardService(session)
            await service.submit(board, a, 10)
            await service.submit(board, b, 30)
            await service.submit(board, c, 50)
            await service.submit(board, a, 5)
            b.leaderboard_opt_in = True
            await session.flush()

            view = await service.standings(board, a, "friends")
            assert [row["name"] for row in view["rows"]] == ["lb-b"]
            assert view["you"] == {"rank": 2, "score": 10.0, "detail": {}, "listed": False}
            c.leaderboard_opt_in = True
            a.leaderboard_opt_in = True
            await session.flush()
            everyone = await service.standings(board, a, "global")
            assert [row["name"] for row in everyone["rows"]] == ["lb-c", "lb-b", "lb-a"]

            roulette = RouletteService(session)
            started = await roulette.start(a)
            again = await roulette.start(a)
            assert started["attempt"]["started_at"] == again["attempt"]["started_at"]
            result = await roulette.submit(a, [None] * len(started["snippet"]["questions"]))
            assert result["finished"] and result["score"] == 0
            with pytest.raises(ValueError):
                await roulette.submit(a, [None])
        finally:
            ids = [user.id for user in users]
            await session.rollback()
            await session.execute(delete(RouletteAttempt).where(RouletteAttempt.user_id.in_(ids)))
            await session.execute(delete(LeaderboardEntry).where(LeaderboardEntry.user_id.in_(ids)))
            await session.execute(delete(Friendship).where(Friendship.requester_id.in_(ids)))
            await session.execute(delete(User).where(User.id.in_(ids)))
            await session.commit()
    await engine.dispose()

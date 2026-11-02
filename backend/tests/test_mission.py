import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.models import SelfRating
from app.services.mission import (
    EntryInfo,
    MissionInputs,
    PassageInfo,
    TechniqueInfo,
    age_phrase,
    build_steps,
    number_steps,
    step_minutes,
    technique_score,
)
from tests.test_keyboard_api import client, needs_db, world

DAY = date(2026, 10, 22)


def passage(pid, start, end, difficulty, label=None):
    return PassageInfo(id=pid, start=start, end=end, label=label, difficulty=difficulty, cue="slowly")


def entry(eid, title, *, difficulty=50.0, decay=0.2, days=3.0, passages=(), techniques=(), current=None, target=None):
    return EntryInfo(
        id=eid,
        piece_id=int(eid.strip("e") or 0),
        title=title,
        composer="Someone",
        status="learning",
        difficulty=difficulty,
        decay=decay,
        days_ago=days,
        current_tempo=current,
        target_tempo=target,
        passages=list(passages),
        techniques=list(techniques),
    )


def technique(tid, name, score):
    return TechniqueInfo(id=tid, name=name, mechanic=f"{name} mechanic", score=score)


def inputs(entries, techniques=(), **kwargs):
    return MissionInputs(entries=list(entries), techniques=list(techniques), day=DAY, seed="user:2026-10-22", **kwargs)


def kinds(steps):
    return [step["kind"] for step in steps]


def three_pieces():
    return [
        entry("e1", "Etude in C", difficulty=70, decay=0.5, days=9, passages=[passage(11, 5, 8, 8.5, "Fast run"), passage(12, 20, 24, 6.0)], techniques=[1], current=60, target=120),
        entry("e2", "Nocturne", difficulty=45, decay=0.7, days=14, passages=[passage(21, 3, 4, 5.0)], techniques=[2], current=70, target=80),
        entry("e3", "Minuet", difficulty=25, decay=0.05, days=1, passages=[passage(31, 1, 2, 3.0)], techniques=[1, 2], current=90, target=92),
    ]


def test_a_mission_has_a_warm_up_the_hardest_passage_a_review_and_a_play_through():
    steps = build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", 3.0), technique(2, "Trills", 7.5)]))
    assert kinds(steps) == ["warmup", "passage", "review", "playthrough"]
    assert 10 <= sum(step["minutes"] for step in steps) <= 15


def test_every_step_explains_itself_in_one_short_line():
    for steps in (
        build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", 3.0)])),
        build_steps(inputs(three_pieces()[:1])),
        build_steps(inputs([])),
        build_steps(inputs(three_pieces(), first=True)),
    ):
        for step in steps:
            assert step["why"].strip() == step["why"]
            assert "\n" not in step["why"]
            assert 15 <= len(step["why"]) <= 120, step["why"]


def test_the_warm_up_comes_from_the_techniques_the_player_rates_lowest():
    steps = build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", 3.0), technique(2, "Trills", 4.5), technique(9, "Pedalling", 2.0)]))
    warm = steps[0]
    assert warm["technique"] == "Rapid scales"
    assert warm["technique_id"] == 1
    assert "lowest-rated" in warm["why"]
    assert warm["mechanic"] == "Rapid scales mechanic"
    assert warm["star_entry_id"] == "e1"


def test_the_warm_up_changes_when_the_same_technique_was_used_yesterday():
    techniques = [technique(1, "Rapid scales", 3.0), technique(2, "Trills", 4.5)]
    today = build_steps(inputs(three_pieces(), techniques, avoid_technique=1))
    assert today[0]["technique"] == "Trills"
    only = build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", 3.0)], avoid_technique=1))
    assert only[0]["technique"] == "Rapid scales"


def test_the_warm_up_falls_back_to_a_technique_in_the_pieces_then_to_a_generic_pattern():
    unrated = build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", None), technique(2, "Trills", None)]))
    assert unrated[0]["technique"] in {"Rapid scales", "Trills"}
    generic = build_steps(inputs(three_pieces(), []))
    assert generic[0]["technique"] is None
    assert generic[0]["title"] == "Warm up"
    assert "Five-finger" in generic[0]["mechanic"]


def test_strengths_are_not_chosen_as_a_weakness():
    steps = build_steps(inputs(three_pieces(), [technique(1, "Rapid scales", 9.0), technique(2, "Trills", 8.0)]))
    assert "lowest-rated" not in steps[0]["why"]


def test_the_passage_step_picks_the_hardest_passage_that_is_due():
    steps = build_steps(inputs(three_pieces()))
    focus = steps[1]
    assert focus["kind"] == "passage"
    assert focus["passage_id"] == 11
    assert focus["bars"] == "bars 5-8"
    assert focus["entry_id"] == "e1"
    assert "Fast run" in focus["why"]


def test_yesterdays_passage_is_never_repeated_when_there_is_another():
    steps = build_steps(inputs(three_pieces(), avoid_passages={11}))
    assert steps[1]["passage_id"] != 11
    assert all(step["passage_id"] != 11 for step in steps)


def test_when_every_passage_was_used_yesterday_the_step_works_the_piece_instead():
    single = [entry("e1", "Etude in C", passages=[passage(11, 5, 8, 8.5)], techniques=[1])]
    steps = build_steps(inputs(single, avoid_passages={11}))
    assert all(step["passage_id"] != 11 for step in steps)
    assert steps[1]["passage_id"] is None
    assert steps[1]["bars"] is None
    assert "no marked passages" in steps[1]["why"]


def test_the_review_is_the_piece_that_has_drifted_most_and_not_the_one_just_drilled():
    steps = build_steps(inputs(three_pieces()))
    review = steps[2]
    assert review["kind"] == "review"
    assert review["entry_id"] == "e2"
    assert "14 days ago" in review["why"]


def test_a_piece_never_played_gets_a_gentle_first_pass_as_the_review():
    pieces = three_pieces()
    pieces[1].days_ago = None
    pieces[1].decay = 0.0
    pieces[2].days_ago = None
    steps = build_steps(inputs(pieces))
    assert steps[2]["entry_id"] in {"e2", "e3"}
    assert "first pass" in steps[2]["why"]


def test_with_one_piece_the_review_revisits_a_different_passage_of_it():
    single = [entry("e1", "Etude in C", passages=[passage(11, 5, 8, 8.5), passage(12, 20, 24, 6.0)], techniques=[1], current=60, target=120)]
    steps = build_steps(inputs(single))
    assert kinds(steps) == ["warmup", "passage", "review", "playthrough"]
    assert steps[1]["passage_id"] == 11
    assert steps[2]["passage_id"] == 12
    assert steps[3]["entry_id"] == "e1"
    assert 10 <= sum(step["minutes"] for step in steps) <= 15


def test_with_one_piece_and_one_passage_the_review_is_played_from_memory():
    single = [entry("e1", "Etude in C", passages=[passage(11, 5, 8, 8.5)])]
    steps = build_steps(inputs(single))
    assert steps[2]["passage_id"] is None
    assert steps[2]["title"].startswith("From memory")


def test_with_one_piece_that_has_no_passages_every_step_still_works():
    single = [entry("e1", "My own tune")]
    steps = build_steps(inputs(single))
    assert kinds(steps) == ["warmup", "passage", "review", "playthrough"]
    assert all(step["passage_id"] is None for step in steps)
    assert steps[1]["entry_id"] == "e1"


def test_the_play_through_is_the_piece_closest_to_its_target_tempo_and_not_the_review():
    steps = build_steps(inputs(three_pieces()))
    assert steps[3]["kind"] == "playthrough"
    assert steps[3]["entry_id"] == "e3"
    assert steps[3]["entry_id"] != steps[2]["entry_id"]


def test_with_no_pieces_the_mission_is_a_warm_up_and_free_play_of_ten_minutes():
    steps = build_steps(inputs([]))
    assert kinds(steps) == ["warmup", "freeplay"]
    assert sum(step["minutes"] for step in steps) == 10
    assert steps[1]["entry_id"] is None


def test_the_first_mission_is_short_and_uses_the_one_piece_chosen():
    single = [entry("e1", "Minuet", passages=[passage(11, 1, 4, 4.0)], techniques=[1], days=None, decay=0.0)]
    steps = build_steps(inputs(single, [technique(1, "Rapid scales", 3.0)], first=True))
    assert kinds(steps) == ["warmup", "passage", "playthrough"]
    assert sum(step["minutes"] for step in steps) <= 6
    assert steps[1]["entry_id"] == "e1"


def test_the_same_day_gives_the_same_mission_and_steps_are_numbered():
    first = number_steps(build_steps(inputs(three_pieces())))
    second = number_steps(build_steps(inputs(three_pieces())))
    assert first == second
    assert [step["index"] for step in first] == [0, 1, 2, 3]


def test_a_suggested_metronome_tempo_is_always_playable():
    for step in build_steps(inputs(three_pieces())):
        assert 40 <= step["tempo_bpm"] <= 180


def test_minutes_logged_follow_the_time_spent_within_sensible_bounds():
    assert step_minutes(0, 5) == 1
    assert step_minutes(61, 5) == 2
    assert step_minutes(5 * 60, 5) == 5
    assert step_minutes(3 * 3600, 5) == 10
    assert step_minutes(3 * 3600, 20) == 30


def test_ages_and_ratings_read_naturally():
    assert age_phrase(None) == "not yet played"
    assert age_phrase(0.4) == "played earlier today"
    assert age_phrase(1.2) == "last played yesterday"
    assert age_phrase(5.9) == "last played 5 days ago"
    assert technique_score(SelfRating.STRUGGLE, None) == 3.0
    assert technique_score(SelfRating.STRENGTH, None) == 8.5
    assert technique_score(SelfRating.NEUTRAL, None) is None
    assert technique_score(SelfRating.NEUTRAL, Decimal("4.5")) == 4.5


async def seed_pieces(world):
    from sqlalchemy import select

    from app.models.models import Passage, PassageSource, PieceTechnique, RepertoireEntry, Technique, UserTechniqueProfile

    async with world.factory() as session:
        techniques = (await session.execute(select(Technique).order_by(Technique.id).limit(2))).scalars().all()
        for item in techniques:
            session.add(PieceTechnique(piece_id=world.ids.piece, technique_id=item.id, weight=Decimal("0.8")))
        session.add(UserTechniqueProfile(user_id=world.ids.user, technique_id=techniques[0].id, self_rating=SelfRating.STRUGGLE, proficiency_score=Decimal("2.50")))
        hard = Passage(piece_id=world.ids.piece, start_measure=5, end_measure=8, label="Octave run", difficulty_score=Decimal("8.5"), source=PassageSource.CATALOG)
        easy = Passage(piece_id=world.ids.piece, start_measure=20, end_measure=24, label="Coda", difficulty_score=Decimal("6.0"), source=PassageSource.CATALOG)
        other = Passage(piece_id=world.ids.spare, start_measure=1, end_measure=4, label="Opening", difficulty_score=Decimal("4.0"), source=PassageSource.CATALOG)
        session.add_all([hard, easy, other])
        entry_row = await session.get(RepertoireEntry, world.ids.entry)
        entry_row.last_practiced_at = datetime.now(timezone.utc) - timedelta(days=6)
        await session.commit()
        return SimpleIds(hard=hard.id, easy=easy.id, other=other.id, technique=techniques[0].id)


class SimpleIds:
    def __init__(self, **values):
        self.__dict__.update(values)


async def get_mission(http, **params):
    response = await http.get("/api/v1/practice/mission", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def finish_step(http, mission, index, status="done", seconds=300):
    return await http.post(f"/api/v1/practice/mission/{mission['id']}/steps/{index}", json={"status": status, "seconds": seconds})


@needs_db
async def test_the_endpoint_builds_one_stable_mission_a_day_from_the_users_data(world):
    ids = await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http)
        again = await get_mission(http)
    assert mission["id"] == again["id"]
    assert [step["kind"] for step in mission["steps"]] == ["warmup", "passage", "review", "playthrough"]
    assert mission["kind"] == "daily"
    assert 10 <= mission["total_minutes"] <= 15
    assert mission["next_index"] == 0
    assert mission["steps"][0]["technique_id"] == ids.technique
    assert mission["steps"][1]["passage_id"] == ids.hard
    assert mission["steps"][1]["entry_id"] == str(world.ids.entry)
    assert mission["steps"][2]["entry_id"] == str(world.ids.bare)


@needs_db
async def test_yesterdays_passage_is_not_chosen_again_today(world):
    from app.models.models import Mission

    ids = await seed_pieces(world)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    async with world.factory() as session:
        session.add(
            Mission(user_id=world.ids.user, day=yesterday, steps=[{"index": 1, "kind": "passage", "passage_id": ids.hard}, {"index": 0, "kind": "warmup", "technique_id": ids.technique}], progress=[])
        )
        await session.commit()
    async with client() as http:
        mission = await get_mission(http)
    assert mission["steps"][1]["passage_id"] == ids.easy
    assert all(step["passage_id"] != ids.hard for step in mission["steps"])
    assert mission["steps"][0]["technique_id"] != ids.technique or mission["steps"][0]["technique_id"] is None


@needs_db
async def test_a_passage_practised_by_hand_yesterday_is_avoided_too(world):
    from app.models.models import PracticeSession, SessionItem

    ids = await seed_pieces(world)
    async with world.factory() as session:
        before = datetime.now(timezone.utc) - timedelta(days=1)
        practice = PracticeSession(user_id=world.ids.user, started_at=before, ended_at=before + timedelta(minutes=10))
        session.add(practice)
        await session.flush()
        session.add(SessionItem(session_id=practice.id, repertoire_entry_id=world.ids.entry, passage_id=ids.hard, minutes=10))
        await session.commit()
    async with client() as http:
        mission = await get_mission(http)
    assert mission["steps"][1]["passage_id"] != ids.hard


@needs_db
async def test_a_piece_an_admin_has_hidden_is_left_out_of_the_mission(world):
    from app.models.models import Piece

    await seed_pieces(world)
    async with world.factory() as session:
        piece = await session.get(Piece, world.ids.piece)
        piece.hidden_at = datetime.now(timezone.utc)
        await session.commit()
    async with client() as http:
        mission = await get_mission(http)
    assert all(step.get("entry_id") != str(world.ids.entry) for step in mission["steps"])


@needs_db
async def test_a_user_with_no_pieces_still_gets_a_mission(world):
    from sqlalchemy import delete

    from app.models.models import RepertoireEntry

    async with world.factory() as session:
        await session.execute(delete(RepertoireEntry).where(RepertoireEntry.user_id == world.ids.user))
        await session.commit()
    async with client() as http:
        mission = await get_mission(http)
    assert [step["kind"] for step in mission["steps"]] == ["warmup", "freeplay"]
    assert mission["total_minutes"] == 10


@needs_db
async def test_the_first_mission_is_short(world):
    await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http, first="true")
    assert mission["kind"] == "first"
    assert [step["kind"] for step in mission["steps"]] == ["warmup", "passage", "playthrough"]
    assert mission["total_minutes"] <= 6


@needs_db
async def test_finishing_steps_logs_practice_lights_the_star_and_pays_out_at_the_end(world):
    from sqlalchemy import select

    from app.models.models import PracticeSession, RepertoireEntry, SessionItem

    await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http)
        steps = mission["steps"]
        first = await finish_step(http, mission, 0, seconds=120)
        assert first.status_code == 200
        body = first.json()
        assert body["finished"] is False
        assert body["lit"]["entry_id"] == steps[0]["star_entry_id"]
        assert body["mission"]["next_index"] == 1
        second = await finish_step(http, mission, 1, seconds=300)
        assert second.json()["lit"]["piece_title"] == steps[1]["piece_title"]
        skipped = await finish_step(http, mission, 2, status="skipped", seconds=0)
        assert skipped.json()["lit"] is None
        assert skipped.json()["finished"] is False
        last = await finish_step(http, mission, 3, seconds=240)
    final = last.json()
    assert final["finished"] is True
    assert final["xp"] > 0
    assert final["mission"]["completed_at"] is not None
    assert final["mission"]["next_index"] is None
    assert [item["status"] for item in final["mission"]["progress"]] == ["done", "done", "skipped", "done"]
    assert final["streak"]["today_done"] is True
    async with world.factory() as session:
        practice = (await session.execute(select(PracticeSession).where(PracticeSession.user_id == world.ids.user))).scalars().all()
        assert len(practice) == 1 and practice[0].ended_at is not None
        items = (await session.execute(select(SessionItem).where(SessionItem.session_id == practice[0].id))).scalars().all()
        assert sorted(item.minutes for item in items) == [2, 4, 5]
        practised = await session.get(RepertoireEntry, world.ids.entry)
        assert (datetime.now(timezone.utc) - practised.last_practiced_at).total_seconds() < 120


@needs_db
async def test_a_step_finished_twice_is_counted_once(world):
    from sqlalchemy import func, select

    from app.models.models import SessionItem

    await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http)
        await finish_step(http, mission, 1, seconds=200)
        repeat = await finish_step(http, mission, 1, seconds=200)
        assert repeat.status_code == 200
        assert repeat.json()["lit"] is None
        assert len(repeat.json()["mission"]["progress"]) == 1
    async with world.factory() as session:
        count = (await session.execute(select(func.count()).select_from(SessionItem))).scalar_one()
        assert count >= 1
        mine = (await session.execute(select(func.count()).select_from(SessionItem).where(SessionItem.passage_id == mission["steps"][1]["passage_id"]))).scalar_one()
        assert mine == 1


@needs_db
async def test_skipping_every_step_still_finishes_without_logging_anything(world):
    from sqlalchemy import func, select

    from app.models.models import SessionItem

    await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http)
        for index in range(len(mission["steps"])):
            response = await finish_step(http, mission, index, status="skipped", seconds=0)
        body = response.json()
    assert body["finished"] is True
    assert body["xp"] == 0
    assert body["streak"]["today_done"] is False
    async with world.factory() as session:
        count = (await session.execute(select(func.count()).select_from(SessionItem).where(SessionItem.repertoire_entry_id.in_([world.ids.entry, world.ids.bare])))).scalar_one()
        assert count == 0


@needs_db
async def test_a_mission_step_joins_a_session_the_user_already_has_open(world):
    from sqlalchemy import select

    from app.models.models import PracticeSession

    await seed_pieces(world)
    async with world.factory() as session:
        opened = PracticeSession(user_id=world.ids.user)
        session.add(opened)
        await session.commit()
        open_id = opened.id
    async with client() as http:
        mission = await get_mission(http)
        for index in range(len(mission["steps"])):
            response = await finish_step(http, mission, index, seconds=180)
    assert response.json()["finished"] is True
    assert response.json()["xp"] == 0
    async with world.factory() as session:
        from sqlalchemy import func

        from app.models.models import SessionItem

        still_open = await session.get(PracticeSession, open_id)
        assert still_open.ended_at is None
        count = (await session.execute(select(func.count()).select_from(SessionItem).where(SessionItem.session_id == open_id))).scalar_one()
        assert count == 4


@needs_db
async def test_unknown_missions_and_steps_are_refused(world):
    await seed_pieces(world)
    async with client() as http:
        mission = await get_mission(http)
        stranger = await http.post(f"/api/v1/practice/mission/{uuid.uuid4()}/steps/0", json={"status": "done", "seconds": 60})
        assert stranger.status_code == 404
        outside = await finish_step(http, mission, 9)
        assert outside.status_code == 404
        bad = await http.post(f"/api/v1/practice/mission/{mission['id']}/steps/0", json={"status": "later", "seconds": 60})
        assert bad.status_code == 422


@needs_db
async def test_missions_belong_to_their_owner(world):
    from app.api.deps import get_current_user
    from app.main import app
    from app.models.models import User

    await seed_pieces(world)
    async with client() as http:
        mine = await get_mission(http)

        async def other_user():
            async with world.factory() as session:
                return await session.get(User, world.ids.other)

        app.dependency_overrides[get_current_user] = other_user
        theirs = await get_mission(http)
        steal = await finish_step(http, mine, 0)
    assert theirs["id"] != mine["id"]
    assert steal.status_code == 404
    assert [step["kind"] for step in theirs["steps"]] == ["warmup", "freeplay"]

import io
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.plans import FREE, PLANS, PRO, PlanLimit, plan_named, require_piece_room
from app.services.billing import grants_pro
from app.services.repertoire import SubmissionService
from tests.test_keyboard_api import client, needs_db, passage, perform, world  # noqa: F401

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
PDF = b"%PDF-1.7\n" + b"0" * 64


def subscription(status, **fields):
    return SimpleNamespace(status=status, current_period_end=None, trial_end=None, **fields)


def test_the_two_plans_are_defined_in_one_place():
    assert set(PLANS) == {"free", "pro"}
    assert FREE.active_pieces == 5 and PRO.active_pieces is None
    assert not FREE.pdf_score_reading and PRO.pdf_score_reading
    assert not FREE.share_cards and PRO.share_cards
    assert not FREE.cloud_sync and PRO.cloud_sync
    assert FREE.keyboard_history_attempts < PRO.keyboard_history_attempts
    assert FREE.tempo_ladder_ceiling < 1.0 == PRO.tempo_ladder_ceiling
    assert plan_named("pro") is PRO and plan_named("nonsense") is FREE and plan_named(None) is FREE


def test_the_ladder_ceiling_scales_the_target_tempo():
    assert FREE.ladder_target(100) == 80
    assert PRO.ladder_target(100) == 100
    assert FREE.ladder_target(1) == 1


def test_free_pieces_stop_at_the_limit_with_a_402_that_explains_why():
    require_piece_room(FREE, FREE.active_pieces - 1)
    with pytest.raises(PlanLimit) as stopped:
        require_piece_room(FREE, FREE.active_pieces)
    assert stopped.value.status_code == 402
    detail = stopped.value.detail
    assert detail["code"] == "plan_limit" and detail["feature"] == "active_pieces"
    assert "5 pieces" in detail["message"]
    assert "Pro" in detail["upgrade"] and "Pro" not in detail["message"]
    require_piece_room(PRO, 10_000)


@pytest.mark.parametrize(
    "status, expected",
    [("active", True), ("trialing", True), ("past_due", True), ("canceled", False), ("unpaid", False), ("incomplete", False), ("incomplete_expired", False), ("paused", False)],
)
def test_only_paying_or_trialing_subscriptions_grant_pro(status, expected):
    assert grants_pro(subscription(status), NOW) is expected


def test_no_subscription_means_free():
    assert grants_pro(None, NOW) is False


def test_a_missed_renewal_webhook_stops_granting_pro_after_a_short_grace():
    ended = subscription("active")
    ended.current_period_end = NOW - timedelta(days=2)
    assert grants_pro(ended, NOW) is True
    ended.current_period_end = NOW - timedelta(days=4)
    assert grants_pro(ended, NOW) is False
    future = subscription("trialing")
    future.trial_end = NOW + timedelta(days=3)
    assert grants_pro(future, NOW) is True


async def set_plan(world, pro):
    from sqlalchemy import delete

    from app.models.models import Subscription

    async with world.factory() as session:
        await session.execute(delete(Subscription).where(Subscription.user_id == world.ids.user))
        if pro:
            session.add(Subscription(user_id=world.ids.user, status="active", stripe_customer_id=f"cus_{uuid.uuid4().hex[:12]}"))
        await session.commit()


async def spare_pieces(world, count):
    from app.models.models import Piece

    async with world.factory() as session:
        pieces = [Piece(title=f"Plan piece {uuid.uuid4().hex[:8]}") for _ in range(count)]
        session.add_all(pieces)
        await session.commit()
        return [piece.id for piece in pieces]


async def forget_pieces(world, ids):
    from sqlalchemy import delete

    from app.models.models import Piece, RepertoireEntry

    async with world.factory() as session:
        await session.execute(delete(RepertoireEntry).where(RepertoireEntry.piece_id.in_(ids)))
        await session.execute(delete(Piece).where(Piece.id.in_(ids)))
        await session.commit()


@needs_db
async def test_the_plan_endpoint_describes_what_the_user_has_and_uses(world):
    async with client() as http:
        pro = (await http.get("/api/v1/billing/plan")).json()
        assert pro["plan"] == "pro" and pro["limits"]["is_pro"] is True and pro["limits"]["active_pieces"] is None
        assert pro["usage"]["active_pieces"] == 2
        assert pro["subscription"]["status"] == "active"
        assert pro["can_start_trial"] is False
        await set_plan(world, False)
        free = (await http.get("/api/v1/billing/plan")).json()
        assert free["plan"] == "free" and free["limits"]["active_pieces"] == 5
        assert free["subscription"] is None and free["can_start_trial"] is True and free["trial_days"] == 7
        assert set(free["messages"]) == {"active_pieces", "pdf_score_reading", "keyboard_history", "tempo_ladder", "share_cards", "cloud_sync"}
        assert "3 keyboard runs" in free["messages"]["keyboard_history"]["message"]
        assert "80%" in free["messages"]["tempo_ladder"]["message"]


@needs_db
async def test_a_free_user_can_keep_five_active_pieces_and_no_more(world):
    await set_plan(world, False)
    extra = await spare_pieces(world, 4)
    try:
        async with client() as http:
            for piece_id in extra[:3]:
                added = await http.post("/api/v1/repertoire", json={"piece_id": piece_id})
                assert added.status_code == 201, added.text
            blocked = await http.post("/api/v1/repertoire", json={"piece_id": extra[3]})
            assert blocked.status_code == 402
            assert blocked.json()["detail"]["code"] == "plan_limit"
            assert blocked.json()["detail"]["feature"] == "active_pieces"
            wishlist = await http.post("/api/v1/repertoire", json={"piece_id": extra[3], "status": "wishlist"})
            assert wishlist.status_code == 201
            entry_id = wishlist.json()["id"]
            activated = await http.patch(f"/api/v1/repertoire/{entry_id}", json={"status": "learning"})
            assert activated.status_code == 402
            kept = await http.patch(f"/api/v1/repertoire/{entry_id}", json={"notes": "someday"})
            assert kept.status_code == 200
            stats = (await http.get("/api/v1/repertoire/stats")).json()
            assert stats["active"] == 5
            shelved = await http.patch(f"/api/v1/repertoire/{world.ids.bare}", json={"status": "retired"})
            assert shelved.status_code == 200
            now_fits = await http.patch(f"/api/v1/repertoire/{entry_id}", json={"status": "polishing"})
            assert now_fits.status_code == 200
    finally:
        await forget_pieces(world, extra)


@needs_db
async def test_a_pro_user_has_no_piece_limit(world):
    extra = await spare_pieces(world, 6)
    try:
        async with client() as http:
            for piece_id in extra:
                assert (await http.post("/api/v1/repertoire", json={"piece_id": piece_id})).status_code == 201
            assert (await http.get("/api/v1/repertoire/stats")).json()["active"] == 8
    finally:
        await forget_pieces(world, extra)


@needs_db
async def test_leaving_pro_keeps_the_pieces_but_stops_new_ones(world):
    extra = await spare_pieces(world, 5)
    try:
        async with client() as http:
            for piece_id in extra[:4]:
                assert (await http.post("/api/v1/repertoire", json={"piece_id": piece_id})).status_code == 201
            await set_plan(world, False)
            assert (await http.get("/api/v1/repertoire/stats")).json()["active"] == 6
            assert (await http.get("/api/v1/repertoire")).status_code == 200
            assert (await http.post("/api/v1/repertoire", json={"piece_id": extra[4]})).status_code == 402
    finally:
        await forget_pieces(world, extra)


@needs_db
async def test_reading_a_pdf_score_is_pro_but_digital_scores_stay_free(world, monkeypatch):
    async def reaches_the_service(*args, **kwargs):
        raise LookupError("repertoire entry not found")

    monkeypatch.setattr(SubmissionService, "add_pdf", reaches_the_service)
    url = f"/api/v1/repertoire/{world.ids.entry}/submissions/score"
    musicxml = b'<?xml version="1.0"?><score-partwise version="4.0"></score-partwise>'
    await set_plan(world, False)
    async with client() as http:
        refused = await http.post(url, files={"file": ("score.pdf", io.BytesIO(PDF))})
        assert refused.status_code == 402
        assert refused.json()["detail"]["feature"] == "pdf_score_reading"
        digital = await http.post(url, files={"file": ("score.musicxml", io.BytesIO(musicxml))})
        assert digital.status_code == 404
        await set_plan(world, True)
        allowed = await http.post(url, files={"file": ("score.pdf", io.BytesIO(PDF))})
        assert allowed.status_code == 404


async def save_runs(http, entry, count, tempo=60):
    notes = (await passage(http, entry, 1, 2))["notes"]
    body = {"mode": "scored", "start_bar": 1, "end_bar": 2, "tempo_bpm": tempo, "duration_sec": 10, "notes": perform(notes, tempo)}
    for _ in range(count):
        response = await http.post(f"/api/v1/keyboard/entries/{entry}/attempts", json=body)
        assert response.status_code == 201, response.text


@needs_db
async def test_free_keeps_only_the_latest_keyboard_runs_in_view_while_pro_sees_them_all(world):
    async with client() as http:
        await save_runs(http, world.ids.entry, 5)
        assert len((await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", params={"limit": 20})).json()) == 5
        heat = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 1, "end_bar": 2})).json()
        assert heat["attempts"] == 5
        await set_plan(world, False)
        seen = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", params={"limit": 20})).json()
        assert len(seen) == FREE.keyboard_history_attempts
        heat = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/heat", params={"start_bar": 1, "end_bar": 2})).json()
        assert heat["attempts"] == FREE.keyboard_history_attempts
        await set_plan(world, True)
        assert len((await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", params={"limit": 20})).json()) == 5


@needs_db
async def test_runs_are_still_stored_in_full_on_free_so_upgrading_brings_the_history_back(world):
    from sqlalchemy import func, select

    from app.models.models import KeyboardAttempt

    await set_plan(world, False)
    async with client() as http:
        await save_runs(http, world.ids.entry, 4)
    async with world.factory() as session:
        stored = (await session.execute(select(func.count()).select_from(KeyboardAttempt).where(KeyboardAttempt.repertoire_entry_id == world.ids.entry))).scalar_one()
    assert stored == 4


@needs_db
async def test_the_free_tempo_ladder_stops_short_of_the_target_and_says_so(world):
    await set_plan(world, False)
    async with client() as http:
        await save_runs(http, world.ids.entry, 2, tempo=80)
        state = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/ladder", params={"start_bar": 1, "end_bar": 2})).json()
        assert state["target_tempo"] == 80 and state["full_target_tempo"] == 100
        assert state["at_plan_limit"] is True and state["reached_target"] is False
        assert state["recommended_tempo"] == 80
        await set_plan(world, True)
        state = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/ladder", params={"start_bar": 1, "end_bar": 2})).json()
        assert state["target_tempo"] == 100 and state["full_target_tempo"] is None
        assert state["at_plan_limit"] is False and state["recommended_tempo"] == 84

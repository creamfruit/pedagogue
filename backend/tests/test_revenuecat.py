import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings, settings
from app.services.revenuecat import (
    candidate_ids,
    in_our_entitlement,
    interval_of,
    parse_webhook,
    subscription_state,
    verify_authorization,
)
from app.services.stripe_gateway import BadWebhook, BillingUnavailable
from tests.test_billing import NOW as STRIPE_NOW
from tests.test_billing import make_event as stripe_event
from tests.test_billing import post_event as post_stripe_event
from tests.test_billing import stripe_on, subscription_object  # noqa: F401
from tests.test_keyboard_api import client, needs_db, world  # noqa: F401
from tests.test_plans import set_plan

SECRET = "rc_shared_secret_for_tests"
SECOND = 1000
DAY = 86400 * 1000
NOW = int(time.time() * 1000)
WEBHOOK = "/api/v1/billing/revenuecat/webhook"


def rc_event(
    kind,
    user_id,
    *,
    event_id=None,
    product="pedagogue_pro_monthly",
    period="NORMAL",
    expires=NOW + 30 * DAY,
    purchased=NOW,
    at=NOW,
    reason=None,
    store="APP_STORE",
    entitlements=("pro",),
    transaction="2000000111",
    aliases=None,
    app_user=None,
    extra=None,
):
    app_user = app_user if app_user is not None else str(user_id)
    event = {
        "id": event_id or str(uuid.uuid4()),
        "type": kind,
        "app_id": "app_test",
        "app_user_id": app_user,
        "original_app_user_id": app_user,
        "aliases": aliases if aliases is not None else [app_user],
        "product_id": product,
        "entitlement_ids": list(entitlements) if entitlements is not None else None,
        "period_type": period,
        "purchased_at_ms": purchased,
        "expiration_at_ms": expires,
        "event_timestamp_ms": at,
        "store": store,
        "environment": "SANDBOX",
        "transaction_id": transaction,
        "original_transaction_id": transaction,
        "currency": "USD",
        "price": 9.99,
    }
    if reason:
        event["cancel_reason"] = reason
    event.update(extra or {})
    return {"api_version": "1.0", "event": event}


@pytest.fixture
def rc_on(monkeypatch):
    monkeypatch.setattr(settings, "revenuecat_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "revenuecat_entitlement_id", "pro")


async def send(http, body, *, secret=SECRET, header=None):
    headers = {"content-type": "application/json"}
    value = header if header is not None else secret
    if value is not None:
        headers["authorization"] = value
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return await http.post(WEBHOOK, content=raw, headers=headers)


async def plan_of(http):
    return (await http.get("/api/v1/billing/plan")).json()


async def row_of(world):
    from sqlalchemy import select

    from app.models.models import Subscription

    async with world.factory() as session:
        return (await session.execute(select(Subscription).where(Subscription.user_id == world.ids.user))).scalar_one()


def test_a_matching_secret_passes_with_or_without_bearer():
    verify_authorization(SECRET, SECRET)
    verify_authorization(f"Bearer {SECRET}", SECRET)
    verify_authorization(f"  bearer   {SECRET} ", SECRET)


def test_a_wrong_or_missing_secret_is_refused():
    for header in (None, "", "wrong", f"{SECRET}x", "Bearer ", "Bearer wrong", "café"):
        with pytest.raises(BadWebhook):
            verify_authorization(header, SECRET)


def test_the_webhook_is_off_until_a_secret_is_set():
    with pytest.raises(BillingUnavailable):
        verify_authorization(SECRET, "")
    with pytest.raises(BillingUnavailable):
        verify_authorization(SECRET, "   ")


def test_only_a_revenuecat_event_body_is_accepted():
    good = json.dumps(rc_event("RENEWAL", uuid.uuid4())).encode()
    assert parse_webhook(good)["type"] == "RENEWAL"
    for bad in (b"not json", b"[]", b'{"event": 3}', b'{"event": {"id": "x"}}', b'{"event": {"type": "RENEWAL"}}', b'{"hello": "world"}'):
        with pytest.raises(BadWebhook):
            parse_webhook(bad)


def test_the_settings_come_from_the_environment(monkeypatch):
    for name in ("REVENUECAT_WEBHOOK_SECRET", "REVENUECAT_ENTITLEMENT_ID"):
        monkeypatch.delenv(name, raising=False)
    off = Settings(_env_file=None)
    assert off.revenuecat_ready is False and off.revenuecat_entitlement_id == "pro"
    monkeypatch.setenv("REVENUECAT_WEBHOOK_SECRET", " shh ")
    monkeypatch.setenv("REVENUECAT_ENTITLEMENT_ID", "premium")
    on = Settings(_env_file=None)
    assert on.revenuecat_ready is True and on.revenuecat_entitlement_id == "premium"


def test_the_plan_is_read_from_the_product_and_falls_back_to_the_length():
    user = uuid.uuid4()
    assert interval_of(rc_event("RENEWAL", user, product="pedagogue_pro_monthly")["event"]) == "month"
    assert interval_of(rc_event("RENEWAL", user, product="pedagogue_pro_yearly")["event"]) == "year"
    assert interval_of(rc_event("RENEWAL", user, product="pedagogue_pro_yearly:p1y")["event"]) == "year"
    assert interval_of(rc_event("RENEWAL", user, product="pro_annual")["event"]) == "year"
    unnamed = rc_event("RENEWAL", user, product="x", purchased=NOW, expires=NOW + 365 * DAY)["event"]
    assert interval_of(unnamed) == "year"
    short = rc_event("RENEWAL", user, product="x", purchased=NOW, expires=NOW + 31 * DAY)["event"]
    assert interval_of(short) == "month"
    trial = rc_event("INITIAL_PURCHASE", user, product="x", period="TRIAL", purchased=NOW, expires=NOW + 7 * DAY)["event"]
    assert interval_of(trial) is None


def test_candidate_ids_keep_the_order_and_drop_blanks_and_repeats():
    user = str(uuid.uuid4())
    event = rc_event("RENEWAL", user, aliases=["$RCAnonymousID:abc", user, "", None, "$RCAnonymousID:abc"])["event"]
    assert candidate_ids(event) == [user, "$RCAnonymousID:abc"]


def test_events_for_other_entitlements_are_not_ours(monkeypatch):
    monkeypatch.setattr(settings, "revenuecat_entitlement_id", "pro")
    user = uuid.uuid4()
    assert in_our_entitlement(rc_event("RENEWAL", user)["event"]) is True
    assert in_our_entitlement(rc_event("RENEWAL", user, entitlements=("other",))["event"]) is False
    assert in_our_entitlement(rc_event("RENEWAL", user, entitlements=None)["event"]) is True
    assert in_our_entitlement(rc_event("RENEWAL", user, entitlements=None, extra={"entitlement_id": "other"})["event"]) is False
    monkeypatch.setattr(settings, "revenuecat_entitlement_id", "")
    assert in_our_entitlement(rc_event("RENEWAL", user, entitlements=("other",))["event"]) is True


def test_each_kind_of_event_becomes_one_state():
    user = uuid.uuid4()
    now = datetime.fromtimestamp(NOW / 1000, tz=timezone.utc)
    bought = subscription_state(rc_event("INITIAL_PURCHASE", user)["event"], now)
    assert (bought["status"], bought["cancel_at_period_end"], bought["trial"]) == ("active", False, False)
    assert bought["current_period_end"] - now == timedelta(days=30)
    trial = subscription_state(rc_event("INITIAL_PURCHASE", user, period="TRIAL", expires=NOW + 7 * DAY)["event"], now)
    assert (trial["status"], trial["trial"]) == ("trialing", True)
    assert trial["trial_end"] == trial["current_period_end"]
    renewed = subscription_state(rc_event("RENEWAL", user, period="NORMAL")["event"], now)
    assert (renewed["status"], renewed["trial_end"]) == ("active", None)
    cancelled = subscription_state(rc_event("CANCELLATION", user, reason="UNSUBSCRIBE")["event"], now)
    assert (cancelled["status"], cancelled["cancel_at_period_end"]) == ("active", True)
    over = subscription_state(rc_event("CANCELLATION", user, reason="UNSUBSCRIBE", expires=NOW - DAY)["event"], now)
    assert over["status"] == "canceled"
    expired = subscription_state(rc_event("EXPIRATION", user, expires=NOW - SECOND)["event"], now)
    assert expired["status"] == "canceled"
    refunded = subscription_state(rc_event("CANCELLATION", user, reason="CUSTOMER_SUPPORT")["event"], now)
    assert refunded["status"] == "canceled" and refunded["current_period_end"] == now
    billing = subscription_state(rc_event("BILLING_ISSUE", user)["event"], now)
    assert billing["status"] == "past_due"
    assert subscription_state(rc_event("UNCANCELLATION", user)["event"], now)["cancel_at_period_end"] is False


@needs_db
async def test_the_webhook_refuses_a_missing_or_wrong_secret(world, rc_on):
    await set_plan(world, False)
    body = rc_event("INITIAL_PURCHASE", world.ids.user)
    async with client() as http:
        missing = await send(http, body, secret=None)
        wrong = await send(http, body, secret="not-the-secret")
        assert (missing.status_code, wrong.status_code) == (401, 401)
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_the_webhook_says_so_when_it_is_not_switched_on(world, monkeypatch):
    monkeypatch.setattr(settings, "revenuecat_webhook_secret", "")
    async with client() as http:
        response = await send(http, rc_event("INITIAL_PURCHASE", world.ids.user))
    assert response.status_code == 503


@needs_db
async def test_a_signed_post_that_is_not_an_event_is_a_bad_request(world, rc_on):
    async with client() as http:
        assert (await send(http, b"not json")).status_code == 400
        assert (await send(http, {"hello": "world"})).status_code == 400


@needs_db
async def test_a_purchase_sets_pro_and_links_the_customer_to_the_user(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        assert (await plan_of(http))["plan"] == "free"
        response = await send(http, rc_event("INITIAL_PURCHASE", world.ids.user))
        assert response.status_code == 200 and response.json() == {"received": True, "outcome": "applied"}
        pro = await plan_of(http)
        assert pro["plan"] == "pro" and pro["limits"]["is_pro"] is True and pro["limits"]["active_pieces"] is None
        assert pro["subscription"]["status"] == "active" and pro["subscription"]["interval"] == "month"
        assert pro["subscription"]["provider"] == "revenuecat"
        assert pro["subscription"]["cancel_at_period_end"] is False
        assert pro["billing"]["portal"] is False
    row = await row_of(world)
    assert row.revenuecat_customer_id == str(world.ids.user)
    assert row.revenuecat_subscription_id == "2000000111"
    assert row.provider == "revenuecat"


@needs_db
async def test_a_yearly_purchase_on_android_is_recorded_as_yearly(world, rc_on):
    await set_plan(world, False)
    body = rc_event("INITIAL_PURCHASE", world.ids.user, product="pedagogue_pro_yearly:p1y", store="PLAY_STORE", expires=NOW + 365 * DAY, transaction="GPA.3300-1111")
    async with client() as http:
        await send(http, body)
        assert (await plan_of(http))["subscription"]["interval"] == "year"


@needs_db
async def test_a_free_trial_from_the_store_counts_as_pro_and_uses_up_the_trial(world, rc_on):
    await set_plan(world, False)
    ends = NOW + 7 * DAY
    async with client() as http:
        assert (await plan_of(http))["can_start_trial"] is True
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, period="TRIAL", expires=ends))
        trial = await plan_of(http)
        assert trial["plan"] == "pro" and trial["subscription"]["status"] == "trialing"
        assert trial["subscription"]["trial_end"] is not None
        assert trial["can_start_trial"] is False
        await send(http, rc_event("RENEWAL", world.ids.user, period="NORMAL", at=NOW + SECOND, purchased=ends, expires=ends + 30 * DAY))
        paid = await plan_of(http)
        assert paid["subscription"]["status"] == "active" and paid["subscription"]["trial_end"] is None
        assert paid["can_start_trial"] is False


@needs_db
async def test_a_renewal_moves_the_period_end_forward(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, expires=NOW + 30 * DAY))
        first = (await plan_of(http))["subscription"]["current_period_end"]
        renewed = await send(http, rc_event("RENEWAL", world.ids.user, at=NOW + SECOND, purchased=NOW + 30 * DAY, expires=NOW + 60 * DAY))
        assert renewed.json()["outcome"] == "applied"
        after = (await plan_of(http))["subscription"]["current_period_end"]
        assert datetime.fromisoformat(after) - datetime.fromisoformat(first) == timedelta(days=30)
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_cancelling_keeps_pro_until_the_expiration_event(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        cancelled = await send(http, rc_event("CANCELLATION", world.ids.user, reason="UNSUBSCRIBE", at=NOW + SECOND))
        assert cancelled.json()["outcome"] == "applied"
        scheduled = await plan_of(http)
        assert scheduled["plan"] == "pro" and scheduled["subscription"]["cancel_at_period_end"] is True
        ended = await send(http, rc_event("EXPIRATION", world.ids.user, at=NOW + 2 * SECOND, expires=NOW - SECOND, extra={"expiration_reason": "UNSUBSCRIBE"}))
        assert ended.json()["outcome"] == "applied"
        cleared = await plan_of(http)
        assert cleared["plan"] == "free" and cleared["subscription"]["status"] == "canceled"
        assert cleared["limits"]["active_pieces"] == 5


@needs_db
async def test_uncancelling_switches_the_renewal_back_on(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        await send(http, rc_event("CANCELLATION", world.ids.user, reason="UNSUBSCRIBE", at=NOW + SECOND))
        await send(http, rc_event("UNCANCELLATION", world.ids.user, at=NOW + 2 * SECOND))
        back = await plan_of(http)
        assert back["plan"] == "pro" and back["subscription"]["cancel_at_period_end"] is False


@needs_db
async def test_an_expiration_clears_pro_once_the_grace_days_have_passed(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, expires=NOW - 10 * DAY, purchased=NOW - 40 * DAY, at=NOW - 40 * DAY))
        assert (await plan_of(http))["plan"] == "free"
        await send(http, rc_event("RENEWAL", world.ids.user, expires=NOW + 20 * DAY, purchased=NOW - 10 * DAY, at=NOW - 10 * DAY + SECOND))
        assert (await plan_of(http))["plan"] == "pro"
        expired = await send(http, rc_event("EXPIRATION", world.ids.user, expires=NOW, at=NOW + SECOND))
        assert expired.json()["outcome"] == "applied"
        cleared = await plan_of(http)
        assert cleared["plan"] == "free" and cleared["subscription"]["status"] == "canceled"


@needs_db
async def test_a_refund_takes_pro_away_straight_away(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        assert (await plan_of(http))["plan"] == "pro"
        refund = await send(http, rc_event("CANCELLATION", world.ids.user, reason="CUSTOMER_SUPPORT", at=NOW + SECOND, expires=NOW + 29 * DAY))
        assert refund.json()["outcome"] == "applied"
        refunded = await plan_of(http)
        assert refunded["plan"] == "free" and refunded["subscription"]["status"] == "canceled"
        assert refunded["subscription"]["cancel_at_period_end"] is False
        reversed_ = await send(http, rc_event("REFUND_REVERSED", world.ids.user, at=NOW + 2 * SECOND))
        assert reversed_.json()["outcome"] == "applied"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_a_billing_problem_keeps_pro_while_the_store_retries(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        problem = await send(http, rc_event("BILLING_ISSUE", world.ids.user, at=NOW + SECOND, expires=NOW + 3 * DAY))
        assert problem.json()["outcome"] == "applied"
        retrying = await plan_of(http)
        assert retrying["plan"] == "pro" and retrying["subscription"]["status"] == "past_due"
        await send(http, rc_event("EXPIRATION", world.ids.user, at=NOW + 2 * SECOND, expires=NOW, extra={"expiration_reason": "BILLING_ERROR"}))
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_an_event_delivered_twice_is_applied_once(world, rc_on):
    await set_plan(world, False)
    body = rc_event("INITIAL_PURCHASE", world.ids.user, event_id=str(uuid.uuid4()))
    async with client() as http:
        first = await send(http, body)
        second = await send(http, body)
        assert first.json()["outcome"] == "applied" and second.json()["outcome"] == "duplicate"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_an_older_event_arriving_late_cannot_undo_a_newer_one(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("RENEWAL", world.ids.user, at=NOW + 100 * SECOND))
        late = await send(http, rc_event("EXPIRATION", world.ids.user, at=NOW + 50 * SECOND, expires=NOW))
        assert late.json()["outcome"] == "stale"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_events_that_are_not_about_a_subscription_change_are_ignored(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        for kind in ("TEST", "TRANSFER", "SUBSCRIPTION_PAUSED", "NON_RENEWING_PURCHASE", "INVOICE_ISSUANCE"):
            ignored = await send(http, rc_event(kind, world.ids.user))
            assert ignored.status_code == 200 and ignored.json()["outcome"] == "ignored", kind
        other = await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, entitlements=("something_else",)))
        assert other.json()["outcome"] == "ignored"
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_people_we_do_not_know_get_a_200_so_the_event_is_not_retried(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        stranger = await send(http, rc_event("INITIAL_PURCHASE", uuid.uuid4()))
        assert stranger.status_code == 200 and stranger.json()["outcome"] == "unknown user"
        anonymous = await send(http, rc_event("INITIAL_PURCHASE", None, app_user="$RCAnonymousID:0123456789abcdef"))
        assert anonymous.json()["outcome"] == "unknown user"
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_an_anonymous_purchase_is_found_through_the_alias_of_the_logged_in_user(world, rc_on):
    await set_plan(world, False)
    body = rc_event(
        "INITIAL_PURCHASE",
        None,
        app_user="$RCAnonymousID:0123456789abcdef",
        aliases=["$RCAnonymousID:0123456789abcdef", str(world.ids.user)],
    )
    async with client() as http:
        assert (await send(http, body)).json()["outcome"] == "applied"
        assert (await plan_of(http))["plan"] == "pro"
    assert (await row_of(world)).revenuecat_customer_id == str(world.ids.user)


@needs_db
async def test_an_older_subscription_ending_does_not_end_a_newer_one(world, rc_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, transaction="old", at=NOW))
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, transaction="new", product="pedagogue_pro_yearly", expires=NOW + 365 * DAY, at=NOW + SECOND))
        late = await send(http, rc_event("EXPIRATION", world.ids.user, transaction="old", at=NOW + 2 * SECOND, expires=NOW))
        assert late.json()["outcome"] == "stale"
        current = await plan_of(http)
        assert current["plan"] == "pro" and current["subscription"]["interval"] == "year"


@needs_db
async def test_a_subscriber_on_the_website_stays_pro_when_a_store_subscription_ends(world, rc_on, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_stripe_event(http, stripe_event("customer.subscription.created", subscription_object(world.ids.user), created=STRIPE_NOW))
        assert (await plan_of(http))["subscription"]["provider"] == "stripe"
        ended = await send(http, rc_event("EXPIRATION", world.ids.user, expires=NOW, at=NOW + 5 * SECOND))
        assert ended.json()["outcome"] == "stale"
        refund = await send(http, rc_event("CANCELLATION", world.ids.user, reason="CUSTOMER_SUPPORT", at=NOW + 6 * SECOND))
        assert refund.json()["outcome"] == "stale"
        still = await plan_of(http)
        assert still["plan"] == "pro" and still["subscription"]["provider"] == "stripe"


@needs_db
async def test_a_subscriber_in_the_app_stays_pro_when_a_website_subscription_ends(world, rc_on, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        assert (await plan_of(http))["subscription"]["provider"] == "revenuecat"
        ended = await post_stripe_event(
            http, stripe_event("customer.subscription.deleted", subscription_object(world.ids.user, status="canceled"), created=STRIPE_NOW + 60)
        )
        assert ended.json()["outcome"] == "stale"
        still = await plan_of(http)
        assert still["plan"] == "pro" and still["subscription"]["provider"] == "revenuecat"


@needs_db
async def test_pro_on_any_platform_unlocks_the_same_limits_everywhere(world, rc_on, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        free = await plan_of(http)
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user))
        from_store = await plan_of(http)
        await set_plan(world, False)
        await post_stripe_event(http, stripe_event("customer.subscription.created", subscription_object(world.ids.user)))
        from_website = await plan_of(http)
    assert free["limits"]["is_pro"] is False
    assert from_store["limits"] == from_website["limits"]
    assert from_store["limits"]["is_pro"] is True and from_store["limits"]["cloud_sync"] is True


@needs_db
async def test_buying_on_the_website_after_a_store_subscription_ended_takes_over(world, rc_on, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, at=NOW))
        await send(http, rc_event("EXPIRATION", world.ids.user, expires=NOW - 10 * DAY, at=NOW + SECOND))
        assert (await plan_of(http))["plan"] == "free"
        await post_stripe_event(http, stripe_event("customer.subscription.created", subscription_object(world.ids.user, sub="sub_after"), created=STRIPE_NOW + 3600))
        taken = await plan_of(http)
        assert taken["plan"] == "pro" and taken["subscription"]["provider"] == "stripe"
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user, transaction="again", at=NOW + 2 * 3600 * SECOND))
        assert (await plan_of(http))["subscription"]["provider"] == "revenuecat"


@needs_db
async def test_the_subscriber_list_shows_where_a_subscription_came_from(world, rc_on, monkeypatch):
    from tests.test_billing import email_of

    await set_plan(world, False)
    monkeypatch.setattr(settings, "admin_emails_raw", await email_of(world, world.ids.user))
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user))
        listed = (await http.get("/api/v1/admin/subscribers", params={"limit": 200})).json()
        mine = next(item for item in listed["items"] if item["user_id"] == str(world.ids.user))
        assert mine["provider"] == "revenuecat" and mine["is_pro"] is True and mine["interval"] == "month"


@needs_db
async def test_deleting_an_account_with_a_store_subscription_never_calls_stripe(world, rc_on, stripe_on, monkeypatch):
    from app.api.v1 import auth as auth_api

    monkeypatch.setattr(auth_api.hasher, "verify", lambda *args: True)
    await set_plan(world, False)
    async with client() as http:
        await send(http, rc_event("INITIAL_PURCHASE", world.ids.user))
        gone = await http.request("DELETE", "/api/v1/auth/me", json={"confirmation": "DELETE", "password": "whatever"})
        assert gone.status_code == 204
    assert not [call for call in stripe_on.calls if call[0] == "cancel"]

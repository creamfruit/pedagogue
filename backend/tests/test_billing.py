import hashlib
import hmac
import json
import time
import uuid

import pytest
import stripe

from app.api.v1 import billing as billing_api
from app.core.config import Settings, settings
from app.main import app
from app.services.stripe_gateway import BadWebhook, BillingUnavailable, StripeGateway, get_gateway, verify_webhook
from tests.test_keyboard_api import client, needs_db, world  # noqa: F401
from tests.test_plans import set_plan

SECRET = "whsec_test_secret"
MONTH = "price_month_test"
YEAR = "price_year_test"
NOW = int(time.time())
DAY = 86400


def sign(body: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    stamp = int(timestamp if timestamp is not None else time.time())
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def subscription_object(user_id, *, sub="sub_1", customer="cus_1", status="active", price=MONTH, trial_end=None, period_end=NOW + 30 * DAY, cancel=False, metadata=True):
    interval = "year" if price == YEAR else "month"
    return {
        "id": sub,
        "object": "subscription",
        "customer": customer,
        "status": status,
        "cancel_at_period_end": cancel,
        "trial_end": trial_end,
        "metadata": {"user_id": str(user_id)} if metadata else {},
        "items": {"data": [{"price": {"id": price, "recurring": {"interval": interval}}, "current_period_end": period_end}]},
    }


def make_event(kind, obj, *, event_id=None, created=None):
    return {"id": event_id or f"evt_{uuid.uuid4().hex[:14]}", "object": "event", "type": kind, "created": created or NOW, "data": {"object": obj}}


class FakeGateway(StripeGateway):
    def __init__(self):
        super().__init__("sk_test_fake")
        self.calls = []
        self.subscriptions = {}
        self.fail_cancel = False

    def create_customer(self, email, user_id):
        self.calls.append(("customer", email, user_id))
        return f"cus_{uuid.uuid4().hex[:10]}"

    def create_checkout(self, **kwargs):
        self.calls.append(("checkout", kwargs))
        return "https://checkout.stripe.test/c/session"

    def create_portal(self, **kwargs):
        self.calls.append(("portal", kwargs))
        return "https://billing.stripe.test/p/session"

    def retrieve_subscription(self, subscription_id):
        self.calls.append(("retrieve", subscription_id))
        return self.subscriptions[subscription_id]

    def cancel_subscription(self, subscription_id):
        self.calls.append(("cancel", subscription_id))
        if self.fail_cancel:
            raise stripe.APIConnectionError("stripe is down")

    def price_summary(self, price_id):
        return {"amount": 900 if price_id == MONTH else 7900, "currency": "usd", "interval": "month" if price_id == MONTH else "year"}


@pytest.fixture
def stripe_on(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "stripe_price_monthly", MONTH)
    monkeypatch.setattr(settings, "stripe_price_yearly", YEAR)
    monkeypatch.setattr(settings, "stripe_trial_days", 7)
    monkeypatch.setattr(settings, "website_url", "https://pedagogue.test")
    billing_api._price_cache.clear()
    fake = FakeGateway()
    app.dependency_overrides[get_gateway] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_gateway, None)


def test_prices_and_readiness_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    monkeypatch.setenv("STRIPE_PRICE_MONTHLY", "price_m")
    monkeypatch.setenv("STRIPE_PRICE_YEARLY", " price_y ")
    loaded = Settings(_env_file=None)
    assert loaded.stripe_prices == {"month": "price_m", "year": "price_y"}
    assert loaded.stripe_checkout_ready is True
    assert loaded.stripe_trial_days == 7


def test_checkout_needs_a_key_and_at_least_one_price(monkeypatch):
    for name in ("STRIPE_SECRET_KEY", "STRIPE_PRICE_MONTHLY", "STRIPE_PRICE_YEARLY"):
        monkeypatch.delenv(name, raising=False)
    assert Settings(_env_file=None).stripe_checkout_ready is False
    assert Settings(_env_file=None, stripe_secret_key="sk").stripe_checkout_ready is False
    assert Settings(_env_file=None, stripe_price_monthly="p").stripe_checkout_ready is False
    assert Settings(_env_file=None, stripe_secret_key="sk", stripe_price_yearly="p").stripe_checkout_ready is True


def test_return_links_use_the_website_and_never_an_app_origin():
    assert Settings(_env_file=None, website_url="https://pedagogue.app/").return_base_url == "https://pedagogue.app"
    local = Settings(_env_file=None, website_url=None, cors_origins_raw="http://localhost:5173")
    assert local.return_base_url == "http://localhost:5173"


def test_a_correctly_signed_webhook_is_accepted():
    body = json.dumps(make_event("customer.subscription.updated", {"id": "sub_1"})).encode()
    event = verify_webhook(body, sign(body), SECRET)
    assert event["type"] == "customer.subscription.updated"


def test_a_webhook_with_the_wrong_secret_is_refused():
    body = json.dumps(make_event("customer.subscription.updated", {})).encode()
    with pytest.raises(BadWebhook):
        verify_webhook(body, sign(body, "whsec_other"), SECRET)


def test_a_tampered_webhook_body_is_refused():
    body = json.dumps(make_event("customer.subscription.updated", {"status": "canceled"})).encode()
    header = sign(body)
    with pytest.raises(BadWebhook):
        verify_webhook(body.replace(b"canceled", b"active"), header, SECRET)


def test_an_old_signed_webhook_is_refused_as_a_replay():
    body = json.dumps(make_event("customer.subscription.updated", {})).encode()
    with pytest.raises(BadWebhook):
        verify_webhook(body, sign(body, timestamp=NOW - 3600), SECRET)


def test_a_missing_signature_or_secret_is_refused():
    body = b"{}"
    with pytest.raises(BadWebhook):
        verify_webhook(body, None, SECRET)
    with pytest.raises(BillingUnavailable):
        verify_webhook(body, sign(body), "")


def test_events_that_are_not_stripe_events_are_refused():
    body = b'{"hello": "world"}'
    with pytest.raises(BadWebhook):
        verify_webhook(body, sign(body), SECRET)


async def post_event(http, event, *, signature=None):
    body = json.dumps(event).encode()
    return await http.post("/api/v1/billing/webhook", content=body, headers={"stripe-signature": signature or sign(body), "content-type": "application/json"})


async def plan_of(http):
    return (await http.get("/api/v1/billing/plan")).json()


@needs_db
async def test_the_webhook_refuses_unsigned_and_wrongly_signed_posts(world, stripe_on):
    await set_plan(world, False)
    event = make_event("customer.subscription.created", subscription_object(world.ids.user))
    async with client() as http:
        missing = await http.post("/api/v1/billing/webhook", content=json.dumps(event).encode())
        wrong = await post_event(http, event, signature=sign(json.dumps(event).encode(), "whsec_wrong"))
        assert (missing.status_code, wrong.status_code) == (400, 400)
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_the_webhook_says_so_when_billing_is_not_switched_on(world, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    async with client() as http:
        response = await post_event(http, make_event("customer.subscription.created", {}))
    assert response.status_code == 503


@needs_db
async def test_a_new_subscription_event_sets_pro(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        assert (await plan_of(http))["plan"] == "free"
        response = await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user)))
        assert response.status_code == 200 and response.json()["outcome"] == "applied"
        pro = await plan_of(http)
        assert pro["plan"] == "pro" and pro["limits"]["is_pro"] is True
        assert pro["subscription"]["status"] == "active" and pro["subscription"]["interval"] == "month"
        assert pro["subscription"]["cancel_at_period_end"] is False
        assert pro["billing"]["portal"] is True


@needs_db
async def test_the_yearly_price_is_recorded_as_a_yearly_plan(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, price=YEAR)))
        assert (await plan_of(http))["subscription"]["interval"] == "year"


@needs_db
async def test_a_trial_counts_as_pro_and_uses_up_the_trial(world, stripe_on):
    await set_plan(world, False)
    trial_end = NOW + 7 * DAY
    async with client() as http:
        assert (await plan_of(http))["can_start_trial"] is True
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, status="trialing", trial_end=trial_end, period_end=trial_end)))
        trial = await plan_of(http)
        assert trial["plan"] == "pro" and trial["subscription"]["status"] == "trialing"
        assert trial["subscription"]["trial_end"] is not None
        assert trial["can_start_trial"] is False


@needs_db
async def test_cancelling_at_period_end_keeps_pro_until_the_deleted_event(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user), created=NOW))
        await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, cancel=True), created=NOW + 5))
        scheduled = await plan_of(http)
        assert scheduled["plan"] == "pro" and scheduled["subscription"]["cancel_at_period_end"] is True
        ended = await post_event(http, make_event("customer.subscription.deleted", subscription_object(world.ids.user, status="canceled", cancel=True), created=NOW + 10))
        assert ended.json()["outcome"] == "applied"
        cleared = await plan_of(http)
        assert cleared["plan"] == "free" and cleared["subscription"]["status"] == "canceled"
        assert cleared["limits"]["active_pieces"] == 5


@needs_db
async def test_failed_payments_keep_pro_while_stripe_retries_then_clear_it(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user), created=NOW))
        await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, status="past_due"), created=NOW + 1))
        assert (await plan_of(http))["plan"] == "pro"
        await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, status="unpaid"), created=NOW + 2))
        assert (await plan_of(http))["plan"] == "free"
        await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, status="active"), created=NOW + 3))
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_an_event_delivered_twice_is_applied_once(world, stripe_on):
    await set_plan(world, False)
    event = make_event("customer.subscription.created", subscription_object(world.ids.user), event_id=f"evt_{uuid.uuid4().hex}")
    async with client() as http:
        first = await post_event(http, event)
        second = await post_event(http, event)
        assert first.json()["outcome"] == "applied" and second.json()["outcome"] == "duplicate"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_an_older_event_arriving_late_cannot_undo_a_newer_one(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, status="active"), created=NOW + 100))
        late = await post_event(http, make_event("customer.subscription.updated", subscription_object(world.ids.user, status="incomplete"), created=NOW + 50))
        assert late.json()["outcome"] == "stale"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_events_found_by_customer_need_no_user_metadata(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        async with world.factory() as session:
            from sqlalchemy import select

            from app.models.models import Subscription

            customer = (await session.execute(select(Subscription.stripe_customer_id).where(Subscription.user_id == world.ids.user))).scalar_one()
        bare = subscription_object(world.ids.user, customer=customer, metadata=False)
        applied = await post_event(http, make_event("customer.subscription.updated", bare))
        assert applied.json()["outcome"] == "applied"
        assert (await plan_of(http))["plan"] == "pro"


@needs_db
async def test_subscriptions_for_other_products_and_unknown_people_are_ignored(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        other = await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, price="price_something_else")))
        assert other.json()["outcome"] == "ignored"
        nobody = await post_event(http, make_event("customer.subscription.created", subscription_object(uuid.uuid4(), customer="cus_nobody")))
        assert nobody.status_code == 200 and nobody.json()["outcome"] == "unknown user"
        irrelevant = await post_event(http, make_event("invoice.paid", {"id": "in_1"}))
        assert irrelevant.json()["outcome"] == "ignored"
        assert (await plan_of(http))["plan"] == "free"


@needs_db
async def test_a_completed_checkout_looks_up_the_subscription_and_sets_pro(world, stripe_on):
    await set_plan(world, False)
    stripe_on.subscriptions["sub_checkout"] = subscription_object(world.ids.user, sub="sub_checkout", customer="cus_checkout", status="trialing", trial_end=NOW + 7 * DAY, metadata=False)
    session_object = {"id": "cs_1", "mode": "subscription", "customer": "cus_checkout", "subscription": "sub_checkout", "client_reference_id": str(world.ids.user)}
    async with client() as http:
        response = await post_event(http, make_event("checkout.session.completed", session_object))
        assert response.json()["outcome"] == "applied"
        assert ("retrieve", "sub_checkout") in stripe_on.calls
        trial = await plan_of(http)
        assert trial["plan"] == "pro" and trial["subscription"]["status"] == "trialing"


@needs_db
async def test_a_one_off_payment_checkout_is_not_a_subscription(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        response = await post_event(http, make_event("checkout.session.completed", {"id": "cs_2", "mode": "payment", "customer": "cus_x"}))
        assert response.json()["outcome"] == "ignored"
        assert not [call for call in stripe_on.calls if call[0] == "retrieve"]


@needs_db
async def test_resubscribing_replaces_the_old_subscription_and_a_late_end_of_the_old_one_is_ignored(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, sub="sub_old"), created=NOW))
        await post_event(http, make_event("customer.subscription.deleted", subscription_object(world.ids.user, sub="sub_old", status="canceled"), created=NOW + 10))
        assert (await plan_of(http))["plan"] == "free"
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, sub="sub_new", price=YEAR), created=NOW + 20))
        assert (await plan_of(http))["plan"] == "pro"
        again = await post_event(http, make_event("customer.subscription.deleted", subscription_object(world.ids.user, sub="sub_old", status="canceled"), created=NOW + 15))
        assert again.json()["outcome"] == "stale"
        current = await plan_of(http)
        assert current["plan"] == "pro" and current["subscription"]["interval"] == "year"


@needs_db
async def test_checkout_starts_a_trial_with_the_chosen_price_and_comes_back_to_the_website(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        response = await http.post("/api/v1/billing/checkout", json={"interval": "year"})
        assert response.status_code == 200 and response.json()["url"].startswith("https://checkout.stripe.test/")
        kind, details = [call for call in stripe_on.calls if call[0] == "checkout"][0]
        assert details["price"] == YEAR and details["trial_days"] == 7
        assert details["user_id"] == str(world.ids.user)
        assert details["success_url"] == "https://pedagogue.test/settings?billing=success"
        assert details["cancel_url"] == "https://pedagogue.test/pricing?billing=cancelled"
        await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        assert len([call for call in stripe_on.calls if call[0] == "customer"]) == 1


@needs_db
async def test_checkout_gives_no_second_trial(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, status="trialing", trial_end=NOW + 7 * DAY), created=NOW))
        await post_event(http, make_event("customer.subscription.deleted", subscription_object(world.ids.user, status="canceled", trial_end=NOW + 7 * DAY), created=NOW + 1))
        assert (await plan_of(http))["can_start_trial"] is False
        await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        kind, details = [call for call in stripe_on.calls if call[0] == "checkout"][0]
        assert details["trial_days"] == 0


@needs_db
async def test_checkout_can_have_the_trial_switched_off(world, stripe_on, monkeypatch):
    monkeypatch.setattr(settings, "stripe_trial_days", 0)
    await set_plan(world, False)
    async with client() as http:
        assert (await plan_of(http))["can_start_trial"] is False
        await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        kind, details = [call for call in stripe_on.calls if call[0] == "checkout"][0]
        assert details["trial_days"] == 0


@needs_db
async def test_checkout_is_refused_for_someone_who_already_has_pro_or_an_unsold_plan(world, stripe_on, monkeypatch):
    async with client() as http:
        already = await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        assert already.status_code == 409 and "already have Pro" in already.json()["detail"]
        await set_plan(world, False)
        monkeypatch.setattr(settings, "stripe_price_yearly", "")
        missing = await http.post("/api/v1/billing/checkout", json={"interval": "year"})
        assert missing.status_code == 409 and "isn't available" in missing.json()["detail"]
        assert (await http.post("/api/v1/billing/checkout", json={"interval": "weekly"})).status_code == 422
        assert not [call for call in stripe_on.calls if call[0] == "checkout"]


@needs_db
async def test_checkout_says_pro_is_not_open_when_stripe_is_not_set_up(world, monkeypatch):
    for name in ("stripe_secret_key", "stripe_price_monthly", "stripe_price_yearly"):
        monkeypatch.setattr(settings, name, "")
    await set_plan(world, False)
    async with client() as http:
        response = await http.post("/api/v1/billing/checkout", json={"interval": "month"})
        assert response.status_code == 503
        assert (await plan_of(http))["billing"] == {"checkout": False, "portal": False, "intervals": []}


@needs_db
async def test_the_customer_portal_opens_for_a_customer_only(world, stripe_on):
    await set_plan(world, False)
    async with client() as http:
        assert (await http.post("/api/v1/billing/portal")).status_code == 404
        await set_plan(world, True)
        opened = await http.post("/api/v1/billing/portal")
        assert opened.status_code == 200 and opened.json()["url"].startswith("https://billing.stripe.test/")
        kind, details = [call for call in stripe_on.calls if call[0] == "portal"][0]
        assert details["return_url"] == "https://pedagogue.test/settings"


@needs_db
async def test_prices_are_public_and_read_from_stripe_once(world, stripe_on):
    async with client() as http:
        shown = (await http.get("/api/v1/billing/prices")).json()
        assert shown["available"] is True and shown["trial_days"] == 7
        assert {(item["interval"], item["amount"], item["currency"]) for item in shown["prices"]} == {("month", 900, "usd"), ("year", 7900, "usd")}


@needs_db
async def test_deleting_an_account_cancels_its_subscription_first(world, stripe_on, monkeypatch):
    from app.api.v1 import auth as auth_api

    monkeypatch.setattr(auth_api.hasher, "verify", lambda *args: True)
    await set_plan(world, False)
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, sub="sub_to_cancel")))
        gone = await http.request("DELETE", "/api/v1/auth/me", json={"confirmation": "DELETE", "password": "whatever"})
        assert gone.status_code == 204
    assert ("cancel", "sub_to_cancel") in stripe_on.calls


@needs_db
async def test_an_account_is_kept_if_its_subscription_cannot_be_cancelled(world, stripe_on, monkeypatch):
    from sqlalchemy import select

    from app.api.v1 import auth as auth_api
    from app.models.models import User

    monkeypatch.setattr(auth_api.hasher, "verify", lambda *args: True)
    await set_plan(world, False)
    stripe_on.fail_cancel = True
    async with client() as http:
        await post_event(http, make_event("customer.subscription.created", subscription_object(world.ids.user, sub="sub_stuck")))
        refused = await http.request("DELETE", "/api/v1/auth/me", json={"confirmation": "DELETE", "password": "whatever"})
        assert refused.status_code == 502 and "has not been deleted" in refused.json()["detail"]
    async with world.factory() as session:
        assert (await session.execute(select(User.id).where(User.id == world.ids.user))).first() is not None


@needs_db
async def test_deleting_a_free_account_never_calls_stripe(world, stripe_on, monkeypatch):
    from app.api.v1 import auth as auth_api

    monkeypatch.setattr(auth_api.hasher, "verify", lambda *args: True)
    await set_plan(world, False)
    async with client() as http:
        gone = await http.request("DELETE", "/api/v1/auth/me", json={"confirmation": "DELETE", "password": "whatever"})
        assert gone.status_code == 204
    assert not [call for call in stripe_on.calls if call[0] == "cancel"]


async def email_of(world, user_id):
    from sqlalchemy import select

    from app.models.models import User

    async with world.factory() as session:
        return (await session.execute(select(User.email).where(User.id == user_id))).scalar_one()


async def give_subscription(world, user_id, status):
    from app.models.models import Subscription

    async with world.factory() as session:
        session.add(Subscription(user_id=user_id, status=status, stripe_customer_id=f"cus_{uuid.uuid4().hex[:12]}", billing_interval="month"))
        await session.commit()


@needs_db
async def test_the_subscriber_list_is_for_admins_only(world, monkeypatch):
    async with client() as http:
        assert (await http.get("/api/v1/admin/subscribers")).status_code == 403
        assert (await http.get("/api/v1/auth/me")).json()["is_admin"] is False
        monkeypatch.setattr(settings, "admin_emails_raw", (await email_of(world, world.ids.user)).upper())
        assert (await http.get("/api/v1/auth/me")).json()["is_admin"] is True
        assert (await http.get("/api/v1/admin/subscribers")).status_code == 200


@needs_db
async def test_the_subscriber_list_shows_who_has_what_and_can_filter_to_pro(world, monkeypatch):
    await give_subscription(world, world.ids.other, "canceled")
    monkeypatch.setattr(settings, "admin_emails_raw", await email_of(world, world.ids.user))
    mine = await email_of(world, world.ids.user)
    theirs = await email_of(world, world.ids.other)
    async with client() as http:
        everyone = (await http.get("/api/v1/admin/subscribers", params={"limit": 200})).json()
        rows = {item["email"]: item for item in everyone["items"]}
        assert rows[mine]["status"] == "active" and rows[mine]["is_pro"] is True and rows[mine]["provider"] == "stripe"
        assert rows[theirs]["status"] == "canceled" and rows[theirs]["is_pro"] is False
        assert everyone["total"] >= 2 and everyone["counts"]["pro"] >= 1
        assert everyone["counts"]["by_status"]["canceled"] >= 1
        pro_only = (await http.get("/api/v1/admin/subscribers", params={"status": "pro", "limit": 200})).json()
        emails = {item["email"] for item in pro_only["items"]}
        assert mine in emails and theirs not in emails
        canceled = (await http.get("/api/v1/admin/subscribers", params={"status": "canceled", "limit": 200})).json()
        assert theirs in {item["email"] for item in canceled["items"]}
        page = (await http.get("/api/v1/admin/subscribers", params={"limit": 1})).json()
        assert len(page["items"]) == 1 and page["total"] == everyone["total"]
        assert (await http.get("/api/v1/admin/subscribers", params={"limit": 0})).status_code == 422

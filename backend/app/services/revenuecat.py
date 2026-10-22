from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.plans import PRO_STATUSES
from app.models.models import Subscription, User
from app.services.billing import BillingService, grants_pro, held_by_another_provider
from app.services.stripe_gateway import BadWebhook, BillingUnavailable

logger = logging.getLogger("piano.revenuecat")

PROVIDER = "revenuecat"

PURCHASE_EVENTS = frozenset(
    {
        "INITIAL_PURCHASE",
        "RENEWAL",
        "PRODUCT_CHANGE",
        "UNCANCELLATION",
        "REFUND_REVERSED",
        "SUBSCRIPTION_EXTENDED",
        "TEMPORARY_ENTITLEMENT_GRANT",
    }
)
HANDLED_EVENTS = PURCHASE_EVENTS | {"CANCELLATION", "EXPIRATION", "BILLING_ISSUE"}

REFUND_REASONS = frozenset({"CUSTOMER_SUPPORT"})
YEARLY_DAYS = 300


def verify_authorization(header: Optional[str], secret: Optional[str] = None) -> None:
    secret = (secret if secret is not None else settings.revenuecat_webhook_secret).strip()
    if not secret:
        raise BillingUnavailable("In-app purchase webhooks aren't switched on.")
    given = (header or "").strip()
    if given.lower().startswith("bearer "):
        given = given[7:].strip()
    if not given or not hmac.compare_digest(given.encode(), secret.encode()):
        raise BadWebhook("that webhook did not carry the shared secret")


def parse_webhook(payload: bytes) -> dict:
    try:
        body = json.loads(payload)
    except ValueError as error:
        raise BadWebhook("that is not JSON") from error
    event = body.get("event") if isinstance(body, dict) else None
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise BadWebhook("that is not a RevenueCat event")
    return event


def moment_ms(value) -> Optional[datetime]:
    if value in (None, 0, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def interval_of(event: dict) -> Optional[str]:
    product = str(event.get("product_id") or "").lower()
    if "year" in product or "annual" in product:
        return "year"
    if "month" in product:
        return "month"
    start, end = moment_ms(event.get("purchased_at_ms")), moment_ms(event.get("expiration_at_ms"))
    if start and end and str(event.get("period_type") or "").upper() == "NORMAL":
        return "year" if (end - start).days >= YEARLY_DAYS else "month"
    return None


def is_refund(event: dict) -> bool:
    return event.get("type") == "CANCELLATION" and str(event.get("cancel_reason") or "").upper() in REFUND_REASONS


def subscription_state(event: dict, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    kind = event["type"]
    trial = str(event.get("period_type") or "").upper() == "TRIAL"
    expires = moment_ms(event.get("expiration_at_ms"))
    state = {
        "status": "trialing" if trial else "active",
        "trial_end": expires if trial else None,
        "current_period_end": expires,
        "cancel_at_period_end": False,
        "interval": interval_of(event),
        "trial": trial,
    }
    if kind == "EXPIRATION":
        state.update(status="canceled", current_period_end=expires or now, trial_end=None)
    elif is_refund(event):
        state.update(status="canceled", current_period_end=min(expires, now) if expires else now, trial_end=None)
    elif kind == "CANCELLATION":
        state["cancel_at_period_end"] = True
        if expires is not None and expires <= now:
            state.update(status="canceled", trial_end=None)
    elif kind == "BILLING_ISSUE":
        state.update(status="past_due", trial_end=None)
    return state


def candidate_ids(event: dict) -> list[str]:
    found = [event.get("app_user_id"), event.get("original_app_user_id"), *(event.get("aliases") or [])]
    seen: list[str] = []
    for value in found:
        text = str(value).strip() if value else ""
        if text and text not in seen:
            seen.append(text)
    return seen


def in_our_entitlement(event: dict) -> bool:
    wanted = settings.revenuecat_entitlement_id.strip()
    given = event.get("entitlement_ids")
    if not given and event.get("entitlement_id"):
        given = [event["entitlement_id"]]
    if not wanted or not given:
        return True
    return wanted in given


class RevenueCatService(BillingService):
    async def row_for(self, event: dict) -> Optional[Subscription]:
        ids = candidate_ids(event)
        if not ids:
            return None
        found = await self.session.execute(select(Subscription).where(Subscription.revenuecat_customer_id.in_(ids)))
        row = found.scalars().first()
        if row is not None:
            return row
        for text in ids:
            user_id = self.parse_id(text)
            if user_id is None or await self.session.get(User, user_id) is None:
                continue
            row = await self.subscription(user_id)
            if row is None:
                row = Subscription(user_id=user_id, status="incomplete")
                self.session.add(row)
            row.revenuecat_customer_id = text
            return row
        return None

    async def handle_event(self, event: dict) -> str:
        kind = event["type"]
        if kind not in HANDLED_EVENTS or not in_our_entitlement(event):
            return "ignored"
        if not await self.first_sight({"id": f"rc:{event['id']}", "type": kind}):
            return "duplicate"
        return await self.apply_event(event)

    async def apply_event(self, event: dict) -> str:
        row = await self.row_for(event)
        if row is None:
            return "unknown user"
        happened = moment_ms(event.get("event_timestamp_ms"))
        if happened and row.last_event_at and happened < row.last_event_at:
            return "stale"
        state = subscription_state(event)
        status = state["status"]
        if held_by_another_provider(row, PROVIDER, status):
            return "stale"
        incoming_id = str(event.get("original_transaction_id") or event.get("transaction_id") or "")[:80] or None
        replaced = row.provider == PROVIDER and row.revenuecat_subscription_id and incoming_id and row.revenuecat_subscription_id != incoming_id
        if replaced and status not in PRO_STATUSES and grants_pro(row):
            return "stale"
        row.provider = PROVIDER
        if incoming_id:
            row.revenuecat_subscription_id = incoming_id
        row.status = status
        row.billing_interval = state["interval"] or row.billing_interval
        row.trial_end = state["trial_end"]
        row.current_period_end = state["current_period_end"]
        row.cancel_at_period_end = state["cancel_at_period_end"]
        if state["trial"]:
            row.trial_used = True
        if happened:
            row.last_event_at = happened
        await self.session.flush()
        logger.info("revenuecat %s for user %s is now %s", event["type"], row.user_id, status)
        return "applied"

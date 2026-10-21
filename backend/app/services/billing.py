from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.plans import FREE, MISSED_RENEWAL_GRACE_DAYS, PRO, PRO_STATUSES, Plan, upgrade_messages
from app.models.models import BillingEvent, RepertoireEntry, RepertoireStatus, Subscription, User
from app.services.onboarding import BaseService

logger = logging.getLogger("piano.billing")

PRICE_CACHE_SECONDS = 3600
_price_cache: dict[str, tuple[float, dict]] = {}

ACTIVE_STATUSES = (RepertoireStatus.LEARNING, RepertoireStatus.POLISHING)


def grants_pro(subscription: Optional[Subscription], now: Optional[datetime] = None) -> bool:
    if subscription is None or subscription.status not in PRO_STATUSES:
        return False
    end = subscription.current_period_end or subscription.trial_end
    if end is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now <= end + timedelta(days=MISSED_RENEWAL_GRACE_DAYS)


class PlanService(BaseService):
    async def subscription(self, user_id: uuid.UUID) -> Optional[Subscription]:
        result = await self.session.execute(select(Subscription).where(Subscription.user_id == user_id))
        return result.scalar_one_or_none()

    async def plan_for(self, user_id: uuid.UUID) -> Plan:
        return PRO if grants_pro(await self.subscription(user_id)) else FREE

    async def active_pieces(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(RepertoireEntry)
            .where(RepertoireEntry.user_id == user_id, RepertoireEntry.status.in_(ACTIVE_STATUSES))
        )
        return int(result.scalar_one())

    async def entitlements(self, user_id: uuid.UUID) -> dict:
        subscription = await self.subscription(user_id)
        plan = PRO if grants_pro(subscription) else FREE
        return {
            "plan": plan.key,
            "name": plan.name,
            "limits": plan.limits(),
            "usage": {"active_pieces": await self.active_pieces(user_id)},
            "subscription": subscription_summary(subscription),
            "can_start_trial": settings.stripe_trial_days > 0 and not plan.is_pro and not (subscription and subscription.trial_used),
            "trial_days": settings.stripe_trial_days,
            "messages": upgrade_messages(FREE),
            "billing": {
                "checkout": settings.stripe_checkout_ready,
                "portal": bool(settings.stripe_secret_key.strip() and subscription and subscription.stripe_customer_id),
                "intervals": sorted(settings.stripe_prices),
            },
        }


def subscription_summary(subscription: Optional[Subscription]) -> Optional[dict]:
    if subscription is None:
        return None
    return {
        "status": subscription.status,
        "interval": subscription.billing_interval,
        "trial_end": subscription.trial_end,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "provider": subscription.provider,
    }


HANDLED_EVENTS = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
)

LIVE_STATUSES = PRO_STATUSES | {"incomplete"}


class CheckoutRefused(Exception):
    pass


async def price_options(gateway) -> list[dict]:
    found = []
    for interval, price_id in settings.stripe_prices.items():
        summary: dict = {}
        cached = _price_cache.get(price_id)
        if cached and cached[0] > time.monotonic():
            summary = cached[1]
        elif settings.stripe_secret_key.strip():
            try:
                summary = await asyncio.to_thread(gateway.price_summary, price_id)
                _price_cache[price_id] = (time.monotonic() + PRICE_CACHE_SECONDS, summary)
            except Exception:
                summary = {}
        found.append({"interval": interval, "amount": summary.get("amount"), "currency": summary.get("currency")})
    return found


def moment(value) -> Optional[datetime]:
    if value in (None, 0, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def first_item(subscription: dict) -> dict:
    items = (subscription.get("items") or {}).get("data") or []
    return items[0] if items else {}


def price_ids(subscription: dict) -> list[str]:
    found = []
    for item in (subscription.get("items") or {}).get("data") or []:
        price = item.get("price") or {}
        if price.get("id"):
            found.append(price["id"])
    return found


def interval_of(subscription: dict) -> Optional[str]:
    ours = {price: interval for interval, price in settings.stripe_prices.items()}
    for price in price_ids(subscription):
        if price in ours:
            return ours[price]
    recurring = (first_item(subscription).get("price") or {}).get("recurring") or {}
    return recurring.get("interval")


def is_ours(subscription: dict) -> bool:
    configured = set(settings.stripe_prices.values())
    if not configured:
        return True
    return bool(configured & set(price_ids(subscription)))


class BillingService(PlanService):
    def __init__(self, session, gateway=None) -> None:
        super().__init__(session)
        self.gateway = gateway

    async def call(self, function, *args, **kwargs):
        return await asyncio.to_thread(function, *args, **kwargs)

    async def customer_for(self, user) -> Subscription:
        subscription = await self.subscription(user.id)
        if subscription is None:
            subscription = Subscription(user_id=user.id, status="incomplete")
            self.session.add(subscription)
        if not subscription.stripe_customer_id:
            subscription.stripe_customer_id = await self.call(self.gateway.create_customer, user.email, str(user.id))
            await self.session.commit()
        await self.session.flush()
        return subscription

    async def checkout_url(self, user, interval: str) -> str:
        prices = settings.stripe_prices
        if interval not in prices:
            raise CheckoutRefused("That plan isn't available yet.")
        existing = await self.subscription(user.id)
        if grants_pro(existing):
            raise CheckoutRefused("You already have Pro. Use Manage billing to change or cancel it.")
        subscription = await self.customer_for(user)
        trial_days = settings.stripe_trial_days if not subscription.trial_used else 0
        base = settings.return_base_url
        return await self.call(
            self.gateway.create_checkout,
            customer=subscription.stripe_customer_id,
            price=prices[interval],
            user_id=str(user.id),
            trial_days=trial_days,
            success_url=f"{base}/settings?billing=success",
            cancel_url=f"{base}/pricing?billing=cancelled",
        )

    async def portal_url(self, user) -> str:
        subscription = await self.subscription(user.id)
        if subscription is None or not subscription.stripe_customer_id:
            raise CheckoutRefused("There's no billing to manage yet.")
        return await self.call(
            self.gateway.create_portal,
            customer=subscription.stripe_customer_id,
            return_url=f"{settings.return_base_url}/settings",
        )

    async def cancel_for_deletion(self, user_id: uuid.UUID) -> bool:
        subscription = await self.subscription(user_id)
        if subscription is None or not subscription.stripe_subscription_id:
            return False
        if subscription.status not in LIVE_STATUSES:
            return False
        if not settings.stripe_secret_key.strip():
            logger.warning("account %s has a live Stripe subscription but no Stripe key is set", user_id)
            return False
        await self.call(self.gateway.cancel_subscription, subscription.stripe_subscription_id)
        return True

    async def first_sight(self, event: dict) -> bool:
        inserted = await self.session.execute(
            pg_insert(BillingEvent)
            .values(id=str(event["id"])[:80], event_type=str(event["type"])[:80])
            .on_conflict_do_nothing(index_elements=[BillingEvent.id])
            .returning(BillingEvent.id)
        )
        return inserted.first() is not None

    async def handle_event(self, event: dict) -> str:
        kind = event["type"]
        if kind not in HANDLED_EVENTS:
            return "ignored"
        if not await self.first_sight(event):
            return "duplicate"
        happened = moment(event.get("created"))
        data = (event.get("data") or {}).get("object") or {}
        if kind == "checkout.session.completed":
            return await self.checkout_completed(data)
        return await self.apply_subscription(data, happened)

    async def checkout_completed(self, session_object: dict) -> str:
        if session_object.get("mode") != "subscription" or not session_object.get("subscription"):
            return "ignored"
        user_id = self.parse_id(session_object.get("client_reference_id"))
        subscription = await self.call(self.gateway.retrieve_subscription, session_object["subscription"])
        metadata = dict(subscription.get("metadata") or {})
        if user_id and not metadata.get("user_id"):
            metadata["user_id"] = str(user_id)
        subscription = {**subscription, "metadata": metadata}
        if not subscription.get("customer"):
            subscription["customer"] = session_object.get("customer")
        return await self.apply_subscription(subscription, None)

    @staticmethod
    def parse_id(value) -> Optional[uuid.UUID]:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError):
            return None

    async def find_row(self, subscription: dict) -> Optional[Subscription]:
        conditions = []
        if subscription.get("id"):
            conditions.append(Subscription.stripe_subscription_id == subscription["id"])
        if subscription.get("customer"):
            conditions.append(Subscription.stripe_customer_id == subscription["customer"])
        if conditions:
            found = await self.session.execute(select(Subscription).where(or_(*conditions)))
            row = found.scalars().first()
            if row is not None:
                return row
        user_id = self.parse_id((subscription.get("metadata") or {}).get("user_id"))
        if user_id is None:
            return None
        row = await self.subscription(user_id)
        if row is not None:
            return row
        if await self.session.get(User, user_id) is None:
            return None
        row = Subscription(user_id=user_id, status="incomplete")
        self.session.add(row)
        return row

    async def apply_subscription(self, subscription: dict, happened: Optional[datetime]) -> str:
        if not is_ours(subscription):
            return "ignored"
        row = await self.find_row(subscription)
        if row is None:
            return "unknown user"
        if happened and row.last_event_at and happened < row.last_event_at:
            return "stale"
        status = str(subscription.get("status") or "incomplete")
        incoming_id = subscription.get("id")
        replaced = row.stripe_subscription_id and incoming_id and row.stripe_subscription_id != incoming_id
        if replaced and status not in PRO_STATUSES and row.status in PRO_STATUSES:
            return "stale"
        if incoming_id:
            row.stripe_subscription_id = incoming_id
        if subscription.get("customer"):
            row.stripe_customer_id = subscription["customer"]
        row.status = status
        row.billing_interval = interval_of(subscription) or row.billing_interval
        row.trial_end = moment(subscription.get("trial_end"))
        row.current_period_end = moment(subscription.get("current_period_end") or first_item(subscription).get("current_period_end"))
        row.cancel_at_period_end = bool(subscription.get("cancel_at_period_end") or subscription.get("cancel_at"))
        if status == "trialing" or subscription.get("trial_end"):
            row.trial_used = True
        if happened:
            row.last_event_at = happened
        await self.session.flush()
        return "applied"

    async def subscribers(self, *, limit: int, offset: int, status: Optional[str] = None) -> dict:
        conditions = []
        if status == "pro":
            conditions.append(Subscription.status.in_(sorted(PRO_STATUSES)))
        elif status:
            conditions.append(Subscription.status == status)
        total = (await self.session.execute(select(func.count()).select_from(Subscription).where(*conditions))).scalar_one()
        rows = await self.session.execute(
            select(Subscription, User.email, User.display_name)
            .join(User, User.id == Subscription.user_id)
            .where(*conditions)
            .order_by(Subscription.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        grouped = await self.session.execute(select(Subscription.status, func.count()).group_by(Subscription.status))
        by_status = {name: int(count) for name, count in grouped.all()}
        now = datetime.now(timezone.utc)
        items = [
            {
                "user_id": row.user_id,
                "email": email,
                "name": display_name,
                "status": row.status,
                "is_pro": grants_pro(row, now),
                "interval": row.billing_interval,
                "provider": row.provider,
                "trial_end": row.trial_end,
                "current_period_end": row.current_period_end,
                "cancel_at_period_end": row.cancel_at_period_end,
                "started_at": row.created_at,
            }
            for row, email, display_name in rows.all()
        ]
        return {
            "total": int(total),
            "items": items,
            "counts": {"by_status": by_status, "pro": sum(count for name, count in by_status.items() if name in PRO_STATUSES)},
        }

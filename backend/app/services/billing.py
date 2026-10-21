from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from app.core.config import settings
from app.core.plans import FREE, MISSED_RENEWAL_GRACE_DAYS, PRO, PRO_STATUSES, Plan, upgrade_messages
from app.models.models import RepertoireEntry, RepertoireStatus, Subscription
from app.services.onboarding import BaseService

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

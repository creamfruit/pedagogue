from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class PlanLimitsOut(BaseModel):
    key: str
    name: str
    active_pieces: Optional[int]
    pdf_score_reading: bool
    keyboard_history_attempts: int
    tempo_ladder_ceiling: float
    share_cards: bool
    cloud_sync: bool
    is_pro: bool


class UsageOut(BaseModel):
    active_pieces: int


class SubscriptionOut(BaseModel):
    status: str
    interval: Optional[str] = None
    trial_end: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    provider: str = "stripe"


class UpgradeCopyOut(BaseModel):
    message: str
    upgrade: str


class BillingStateOut(BaseModel):
    checkout: bool = False
    portal: bool = False
    intervals: list[str] = []


class PlanOut(BaseModel):
    plan: str
    name: str
    limits: PlanLimitsOut
    usage: UsageOut
    subscription: Optional[SubscriptionOut] = None
    can_start_trial: bool
    trial_days: int
    messages: dict[str, UpgradeCopyOut] = {}
    billing: BillingStateOut = BillingStateOut()


class CheckoutIn(BaseModel):
    interval: Literal["month", "year"]


class UrlOut(BaseModel):
    url: str


class PriceOut(BaseModel):
    interval: str
    amount: Optional[int] = None
    currency: Optional[str] = None


class PricesOut(BaseModel):
    available: bool
    trial_days: int
    prices: list[PriceOut]

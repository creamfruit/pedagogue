from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from fastapi import HTTPException, status

FREE_KEY = "free"
PRO_KEY = "pro"


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    active_pieces: Optional[int]
    pdf_score_reading: bool
    keyboard_history_attempts: int
    tempo_ladder_ceiling: float
    share_cards: bool
    cloud_sync: bool

    @property
    def is_pro(self) -> bool:
        return self.key == PRO_KEY

    def ladder_target(self, target_tempo: int) -> int:
        return max(1, round(target_tempo * self.tempo_ladder_ceiling))

    def limits(self) -> dict:
        return asdict(self) | {"is_pro": self.is_pro}


FREE = Plan(
    key=FREE_KEY,
    name="Free",
    active_pieces=5,
    pdf_score_reading=False,
    keyboard_history_attempts=3,
    tempo_ladder_ceiling=0.8,
    share_cards=False,
    cloud_sync=False,
)

PRO = Plan(
    key=PRO_KEY,
    name="Pro",
    active_pieces=None,
    pdf_score_reading=True,
    keyboard_history_attempts=50,
    tempo_ladder_ceiling=1.0,
    share_cards=True,
    cloud_sync=True,
)

PLANS = {FREE.key: FREE, PRO.key: PRO}

PRO_STATUSES = frozenset({"trialing", "active", "past_due"})
MISSED_RENEWAL_GRACE_DAYS = 3

STATEMENTS = {
    "active_pieces": "The Free plan keeps {limit} pieces in progress at a time.",
    "pdf_score_reading": "Reading PDF scores is part of Pro. Digital scores (MusicXML and MIDI) still work on Free.",
    "keyboard_history": "Free keeps your last {limit} keyboard runs in view.",
    "tempo_ladder": "The Free tempo ladder stops at {percent}% of your target tempo.",
    "share_cards": "Share cards are part of Pro.",
    "cloud_sync": "Cloud sync is part of Pro: pieces and notes stay available offline and sync when you reconnect.",
}

PITCHES = {
    "active_pieces": "Finish or shelve one, or move to Pro for as many as you like.",
    "pdf_score_reading": "Move to Pro to have your PDF scores read.",
    "keyboard_history": "Pro keeps and shows the whole history.",
    "tempo_ladder": "Pro carries it all the way to your target.",
    "share_cards": "Move to Pro to share your progress as a card.",
    "cloud_sync": "Move to Pro to turn it on.",
}

FEATURES = tuple(STATEMENTS)


class PlanLimit(HTTPException):
    def __init__(self, feature: str, **values) -> None:
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "plan_limit",
                "feature": feature,
                "message": STATEMENTS[feature].format(**values),
                "upgrade": PITCHES[feature],
            },
        )
        self.feature = feature


def upgrade_messages(plan: Plan = FREE) -> dict:
    values = {"limit": plan.active_pieces or 0, "percent": round(plan.tempo_ladder_ceiling * 100)}
    history = values | {"limit": plan.keyboard_history_attempts}
    return {
        feature: {
            "message": STATEMENTS[feature].format(**(history if feature == "keyboard_history" else values)),
            "upgrade": PITCHES[feature],
        }
        for feature in FEATURES
    }


def plan_named(key: Optional[str]) -> Plan:
    return PLANS.get(key or FREE_KEY, FREE)


def require_pdf_reading(plan: Plan) -> None:
    if not plan.pdf_score_reading:
        raise PlanLimit("pdf_score_reading")


def require_piece_room(plan: Plan, active_now: int) -> None:
    if plan.active_pieces is not None and active_now >= plan.active_pieces:
        raise PlanLimit("active_pieces", limit=plan.active_pieces)

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from app.models.models import SelfRating, UserTechniqueProfile

TIER_ORDER = ("S", "A", "B", "C", "D")

TIER_PROFICIENCY = {
    "S": Decimal("9.0"),
    "A": Decimal("7.2"),
    "B": Decimal("5.5"),
    "C": Decimal("3.5"),
    "D": Decimal("1.5"),
}

TIER_SELF_RATING = {
    "S": SelfRating.STRENGTH,
    "A": SelfRating.STRENGTH,
    "B": SelfRating.NEUTRAL,
    "C": SelfRating.NEUTRAL,
    "D": SelfRating.STRUGGLE,
}


def scale100(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(round(float(value) * 10, 1)))


def clamp100(value: float) -> Decimal:
    return Decimal(str(round(min(max(value, 0.0), 100.0), 1)))


def compute_mechanical_load(
    links: Iterable[tuple[str, float]], load_factor_by_name: dict[str, float]
) -> Decimal:
    weighted = [weight * float(load_factor_by_name.get(name, 1.2)) for name, weight in links]
    if not weighted:
        return Decimal("40.0")
    peak = max(weighted)
    mean = sum(weighted) / len(weighted)
    return clamp100(30.0 + peak * 42.0 + mean * 22.0)


def compute_difficulty_score(
    mechanical_load: Decimal, duration_sec: Optional[int], technique_count: int
) -> Decimal:
    length_factor = min((duration_sec or 180) / 60.0, 14.0) * 1.6
    breadth_factor = min(technique_count, 8) * 1.4
    return clamp100(float(mechanical_load) * 0.72 + length_factor + breadth_factor)


def difficulty_band(score: Optional[Decimal]) -> str:
    if score is None:
        return "unrated"
    value = float(score)
    if value < 30:
        return "beginner"
    if value < 50:
        return "early intermediate"
    if value < 65:
        return "intermediate"
    if value < 80:
        return "late intermediate"
    if value < 90:
        return "advanced"
    return "virtuoso"


def tier_to_profile_values(tier: str) -> tuple[SelfRating, Decimal]:
    key = tier.upper()
    if key not in TIER_PROFICIENCY:
        raise ValueError(f"unknown tier: {tier}")
    return TIER_SELF_RATING[key], TIER_PROFICIENCY[key]


def personalize_difficulty(
    base_difficulty: Optional[Decimal],
    technique_weights: dict[int, float],
    profiles_by_technique_id: dict[int, UserTechniqueProfile],
) -> Optional[Decimal]:
    if base_difficulty is None:
        return None
    if not technique_weights or not profiles_by_technique_id:
        return base_difficulty
    adjustment = 0.0
    touched = 0.0
    for technique_id, weight in technique_weights.items():
        profile = profiles_by_technique_id.get(technique_id)
        if profile is None:
            continue
        touched += weight
        if profile.is_strength:
            adjustment -= weight * 9.0
        elif profile.is_weakness:
            adjustment += weight * 11.0
    if touched == 0:
        return base_difficulty
    return clamp100(float(base_difficulty) + adjustment)


def mastery_for(
    technique_id: int, profiles_by_technique_id: dict[int, UserTechniqueProfile]
) -> tuple[str, str]:
    profile = profiles_by_technique_id.get(technique_id)
    if profile is None:
        return "unranked", "amber"
    return profile.mastery_tier, profile.mastery_color

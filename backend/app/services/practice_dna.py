from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import Composer, Piece, Technique, User, UserTechniqueProfile
from app.services.coach_feedback import tier_for
from app.services.onboarding import BaseService
from app.services.progression import TechniqueVectorService

MIN_RATED = 4
STRONG = 0.5
SOME = 0.2
OPPOSED = -0.2


def demand_profile(vectors: Sequence[dict[int, float]]) -> dict[int, float]:
    pieces = [vector for vector in vectors if vector]
    if not pieces:
        return {}
    totals: dict[int, float] = defaultdict(float)
    for vector in pieces:
        for technique_id, weight in vector.items():
            totals[technique_id] += weight
    total = sum(totals.values())
    return {technique_id: weight / total for technique_id, weight in totals.items()} if total else {}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def similarity(proficiency: dict[int, float], demand: dict[int, float]) -> Optional[float]:
    ids = sorted(proficiency)
    return pearson([proficiency[t] for t in ids], [demand.get(t, 0.0) for t in ids])


def readiness(proficiency: dict[int, float], demand: dict[int, float]) -> tuple[Optional[float], float]:
    covered = {t: share for t, share in demand.items() if t in proficiency}
    weight = sum(covered.values())
    if not weight:
        return None, 0.0
    return sum(share * proficiency[t] for t, share in covered.items()) / weight, weight


def match_label(value: Optional[float]) -> str:
    if value is None:
        return "Not enough to compare"
    if value >= STRONG:
        return "Strong match"
    if value >= SOME:
        return "Some overlap"
    if value > OPPOSED:
        return "Little in common"
    return "Leans on your weaker techniques"


def surname(name: str) -> str:
    return name.split()[-1] if name else name


def summary_line(rows: list[dict], proficiency: dict[int, float], names: dict[int, str]) -> str:
    if len(proficiency) < MIN_RATED:
        return f"Rate at least {MIN_RATED} techniques in the tier quiz to compare your profile with the composers'."
    ranked = [row for row in rows if row["similarity"] is not None]
    if not ranked:
        return "Your tiers are too even to single out a composer: every one of them asks for things you rate the same."
    best = ranked[0]
    mean = sum(proficiency.values()) / len(proficiency)
    strong = [names[item["technique_id"]] for item in best["demand"] if proficiency.get(item["technique_id"], -1) > mean][:2]
    who = surname(best["name"])
    if best["similarity"] < SOME:
        return f"No composer's demands line up clearly with your strengths yet. The nearest is {who}."
    if strong:
        return f"Closest to {who}'s technical demands: that music leans on {' and '.join(s.lower() for s in strong)}, which are among your stronger techniques."
    return f"Closest to {who}'s technical demands."


class PracticeDNAService(BaseService):
    async def build(self, user: User) -> dict:
        techniques = (await self.session.execute(select(Technique).order_by(Technique.id))).scalars().all()
        names = {technique.id: technique.name for technique in techniques}
        profiles = (
            await self.session.execute(select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id))
        ).scalars().all()
        proficiency = {
            profile.technique_id: float(profile.proficiency_score)
            for profile in profiles
            if profile.proficiency_score is not None
        }
        pieces = (
            await self.session.execute(
                select(Piece)
                .options(selectinload(Piece.composer).selectinload(Composer.era))
                .where(Piece.is_user_created.is_(False), Piece.composer_id.is_not(None))
            )
        ).scalars().all()
        vectors = await TechniqueVectorService(self.session).vectors_for([piece.id for piece in pieces])
        by_composer: dict[int, list[Piece]] = defaultdict(list)
        for piece in pieces:
            if vectors.get(piece.id):
                by_composer[piece.composer_id].append(piece)

        rows = []
        for group in by_composer.values():
            composer = group[0].composer
            demand = demand_profile([vectors[piece.id] for piece in group])
            value = similarity(proficiency, demand) if len(proficiency) >= MIN_RATED else None
            ready, covered = readiness(proficiency, demand)
            ordered = sorted(demand.items(), key=lambda item: -item[1])
            rows.append(
                {
                    "id": composer.id,
                    "name": composer.name,
                    "era": composer.era.name if composer.era else None,
                    "pieces": len(group),
                    "similarity": round(value, 3) if value is not None else None,
                    "label": match_label(value),
                    "readiness": round(ready, 2) if ready is not None else None,
                    "readiness_tier": tier_for(Decimal(str(ready))) if ready is not None else None,
                    "coverage": round(covered, 3),
                    "demand": [{"technique_id": t, "name": names.get(t, ""), "share": round(share, 4)} for t, share in ordered],
                }
            )
        rows.sort(key=lambda row: (row["similarity"] is None, -(row["similarity"] or 0), row["name"]))
        closest = next((row for row in rows if row["similarity"] is not None and row["similarity"] >= SOME), None)
        return {
            "techniques": [
                {
                    "id": technique.id,
                    "name": technique.name,
                    "category": technique.category.value,
                    "proficiency": proficiency.get(technique.id),
                    "tier": tier_for(Decimal(str(proficiency[technique.id]))) if technique.id in proficiency else None,
                }
                for technique in techniques
            ],
            "rated": len(proficiency),
            "enough": len(proficiency) >= MIN_RATED,
            "composers": rows,
            "closest": {"id": closest["id"], "name": closest["name"]} if closest else None,
            "summary": summary_line(rows, proficiency, names),
        }

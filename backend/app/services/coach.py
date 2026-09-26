from __future__ import annotations

import random
import uuid
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Analysis,
    Composer,
    Drill,
    DrillType,
    Passage,
    PassageAssessment,
    PassageTechnique,
    Piece,
    PlanStep,
    PlanStepStatus,
    PolyrhythmAttempt,
    PracticePlan,
    RepertoireEntry,
    SelfRating,
    SightReadingExercise,
    Submission,
    Technique,
    TechniqueCategory,
    User,
    UserTechniqueProfile,
)
from app.services.notation import SightReadingForge
from app.services.onboarding import BaseService

CATEGORY_DRILLS: dict[TechniqueCategory, tuple[DrillType, ...]] = {
    TechniqueCategory.DOUBLE_NOTES: (DrillType.RHYTHM_VARIANT, DrillType.HANDS_SEPARATE, DrillType.TRANSPOSITION),
    TechniqueCategory.OCTAVES: (DrillType.RHYTHM_VARIANT, DrillType.HANDS_SEPARATE),
    TechniqueCategory.LEAPS: (DrillType.CORTOT_REDUCTION, DrillType.HANDS_SEPARATE),
    TechniqueCategory.CHORDS: (DrillType.CORTOT_REDUCTION, DrillType.RHYTHM_VARIANT),
    TechniqueCategory.REPEATED_NOTES: (DrillType.RHYTHM_VARIANT,),
    TechniqueCategory.TRILLS: (DrillType.RHYTHM_VARIANT, DrillType.HANDS_SEPARATE),
    TechniqueCategory.STRETCHES: (DrillType.CORTOT_REDUCTION,),
    TechniqueCategory.POLYRHYTHM: (DrillType.POLYRHYTHM, DrillType.HANDS_SEPARATE),
    TechniqueCategory.VOICING: (DrillType.VOICING, DrillType.HANDS_SEPARATE),
    TechniqueCategory.PEDALING: (DrillType.VOICING,),
    TechniqueCategory.DEXTERITY: (DrillType.RHYTHM_VARIANT, DrillType.TRANSPOSITION),
    TechniqueCategory.ENDURANCE: (DrillType.RHYTHM_VARIANT,),
}

RHYTHM_PATTERNS = ["dotted", "reverse-dotted", "triplet-groups", "accent-shift"]
TRANSPOSITIONS = [-2, -1, 1, 2, 3]


class DrillForge(BaseService):
    async def weak_passages(self, user: User, limit: int = 5) -> list[tuple[Passage, float]]:
        stmt = (
            select(
                Passage,
                func.avg(func.coalesce(PassageAssessment.accuracy_score, 0.5)).label("score"),
                func.count(PassageAssessment.id).label("hits"),
            )
            .join(PassageAssessment, PassageAssessment.passage_id == Passage.id)
            .join(Analysis, Analysis.id == PassageAssessment.analysis_id)
            .join(Submission, Submission.id == Analysis.submission_id)
            .join(RepertoireEntry, RepertoireEntry.id == Submission.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id)
            .group_by(Passage.id)
            .order_by("score")
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]

    async def categories_for(self, passage_id: int) -> list[TechniqueCategory]:
        stmt = (
            select(Technique.category)
            .join(PassageTechnique, PassageTechnique.technique_id == Technique.id)
            .where(PassageTechnique.passage_id == passage_id)
            .order_by(PassageTechnique.weight.desc())
        )
        result = await self.session.execute(stmt)
        return list(dict.fromkeys(result.scalars().all()))

    def params_for(self, drill_type: DrillType, passage: Passage, seed: int) -> dict:
        rng = random.Random(seed)
        base = {
            "start_measure": passage.start_measure,
            "end_measure": passage.end_measure,
            "start_tempo_pct": 60,
            "target_tempo_pct": 100,
            "step_pct": 5,
        }
        if drill_type == DrillType.RHYTHM_VARIANT:
            base["patterns"] = rng.sample(RHYTHM_PATTERNS, k=min(3, len(RHYTHM_PATTERNS)))
        elif drill_type == DrillType.TRANSPOSITION:
            base["intervals"] = rng.sample(TRANSPOSITIONS, k=2)
        elif drill_type == DrillType.HANDS_SEPARATE:
            base["order"] = ["left", "right", "together"]
            base["repetitions"] = 4
        elif drill_type == DrillType.CORTOT_REDUCTION:
            base["reduction"] = "blocked-chord skeleton, then open to written texture"
            base["hold_beats"] = 2
        elif drill_type == DrillType.POLYRHYTHM:
            base["ratio"] = rng.choice([[3, 2], [4, 3], [5, 4]])
            base["tap_before_play"] = True
        elif drill_type == DrillType.VOICING:
            base["emphasis"] = rng.choice(["top voice", "inner voice", "bass line"])
            base["dynamic_gap"] = "one dynamic level above accompaniment"
        return base

    async def forge(self, user: User, passage_id: int, count: int = 2) -> list[Drill]:
        passage = await self.session.get(Passage, passage_id)
        if passage is None:
            raise LookupError("passage not found")
        categories = await self.categories_for(passage_id)
        types: list[DrillType] = []
        for category in categories:
            for drill_type in CATEGORY_DRILLS.get(category, ()):
                if drill_type not in types:
                    types.append(drill_type)
        if not types:
            types = [DrillType.RHYTHM_VARIANT, DrillType.HANDS_SEPARATE]

        existing = await self.session.execute(
            select(Drill.drill_type).where(Drill.user_id == user.id, Drill.passage_id == passage_id)
        )
        already = set(existing.scalars().all())
        chosen = [t for t in types if t not in already][:count]

        created: list[Drill] = []
        for index, drill_type in enumerate(chosen):
            drill = Drill(
                user_id=user.id,
                passage_id=passage_id,
                drill_type=drill_type,
                params=self.params_for(drill_type, passage, passage_id * 100 + index),
            )
            self.session.add(drill)
            created.append(drill)
        await self.session.flush()
        return created

    async def forge_from_weaknesses(self, user: User, limit: int = 3) -> list[Drill]:
        weak = await self.weak_passages(user, limit=limit)
        drills: list[Drill] = []
        for passage, _ in weak:
            drills.extend(await self.forge(user, passage.id, count=1))
        return drills

    async def list(self, user: User, limit: int = 50) -> list[Drill]:
        stmt = (
            select(Drill)
            .options(selectinload(Drill.passage).selectinload(Passage.piece), selectinload(Drill.session_items))
            .where(Drill.user_id == user.id)
            .order_by(Drill.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get(self, user: User, drill_id: uuid.UUID) -> Drill:
        stmt = (
            select(Drill)
            .options(selectinload(Drill.passage).selectinload(Passage.piece), selectinload(Drill.session_items))
            .where(Drill.id == drill_id, Drill.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        drill = result.scalar_one_or_none()
        if drill is None:
            raise LookupError("drill not found")
        return drill

    async def delete(self, user: User, drill_id: uuid.UUID) -> None:
        drill = await self.get(user, drill_id)
        await self.session.delete(drill)
        await self.session.flush()


class PlanBuilder(BaseService):
    MODEL = "heuristic-0.1"

    async def movements(self, piece_id: int) -> list[Piece]:
        stmt = (
            select(Piece)
            .where(Piece.parent_piece_id == piece_id)
            .order_by(Piece.movement_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def order_movements(movements: Sequence[Piece]) -> list[Piece]:
        if len(movements) < 2:
            return list(movements)
        scored = []
        for movement in movements:
            difficulty = float(movement.difficulty_score or 50.0)
            duration = movement.duration_sec or 0
            scored.append((difficulty + duration / 600.0, movement))
        scored.sort(key=lambda pair: pair[0])
        ordered = [pair[1] for pair in scored]
        return ordered

    @staticmethod
    def days_for(difficulty: Optional[Decimal], length: int = 1) -> int:
        value = float(difficulty) if difficulty is not None else 5.0
        return max(2, int(round(value * 1.5 + length / 8)))

    async def hard_passages(self, piece_id: int, limit: int = 4) -> list[Passage]:
        stmt = (
            select(Passage)
            .where(Passage.piece_id == piece_id)
            .order_by(Passage.difficulty_score.desc().nulls_last(), Passage.start_measure)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def build(self, user: User, entry: RepertoireEntry) -> PracticePlan:
        piece = entry.piece
        movements = await self.movements(piece.id)
        ordered = self.order_movements(movements)
        steps: list[tuple[Optional[int], Optional[int], str, int]] = []

        if ordered:
            first = ordered[0]
            rationale = (
                f"{piece.title} has {len(ordered)} movements. Start with "
                f"{first.title}, the least demanding, to build the physical and musical "
                "foundation before the heavier movements."
            )
            for index, movement in enumerate(ordered):
                position = "Open with" if index == 0 else "Then take on"
                steps.append(
                    (
                        movement.id,
                        None,
                        f"{position} {movement.title}. Hands separate at 60 percent tempo "
                        "until the text is secure, then build in 5 percent steps.",
                        self.days_for(
                            movement.difficulty_score / 10 if movement.difficulty_score is not None else None
                        ),
                    )
                )
        else:
            rationale = (
                f"{piece.title} is a single movement, so the plan works outward from its "
                "hardest passages before assembling the whole."
            )

        for passage in await self.hard_passages(piece.id):
            steps.append(
                (
                    None,
                    passage.id,
                    f"Isolate {passage.measure_span}. Slow practice, then rhythm variants, "
                    "then join to the surrounding four bars.",
                    self.days_for(passage.difficulty_score, passage.length),
                )
            )

        target = entry.target_tempo_bpm or 0
        steps.append(
            (
                piece.id,
                None,
                "Run the whole work daily at a tempo you can hold cleanly"
                + (f", climbing toward {target} bpm." if target else "."),
                7,
            )
        )
        steps.append(
            (
                piece.id,
                None,
                "Record a full run-through and submit it for a readiness score.",
                3,
            )
        )

        plan = PracticePlan(repertoire_entry_id=entry.id, model=self.MODEL, rationale=rationale)
        self.session.add(plan)
        await self.session.flush()

        for order, (piece_id, passage_id, instruction, est_days) in enumerate(steps, start=1):
            self.session.add(
                PlanStep(
                    plan_id=plan.id,
                    step_order=order,
                    piece_id=piece_id,
                    passage_id=passage_id,
                    instruction=instruction,
                    est_days=est_days,
                    status=PlanStepStatus.ACTIVE if order == 1 else PlanStepStatus.TODO,
                )
            )
        await self.session.flush()
        return await self.get(user, plan.id)

    @staticmethod
    def plan_options():
        return (
            selectinload(PracticePlan.steps).selectinload(PlanStep.passage),
            selectinload(PracticePlan.steps).selectinload(PlanStep.piece).selectinload(Piece.composer),
            selectinload(PracticePlan.repertoire_entry)
            .selectinload(RepertoireEntry.piece)
            .selectinload(Piece.composer),
        )

    async def get(self, user: User, plan_id: uuid.UUID) -> PracticePlan:
        stmt = (
            select(PracticePlan)
            .options(*self.plan_options())
            .join(RepertoireEntry, RepertoireEntry.id == PracticePlan.repertoire_entry_id)
            .where(PracticePlan.id == plan_id, RepertoireEntry.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()
        if plan is None:
            raise LookupError("practice plan not found")
        return plan

    async def list_for_entry(self, user: User, entry_id: uuid.UUID) -> list[PracticePlan]:
        stmt = (
            select(PracticePlan)
            .options(*self.plan_options())
            .join(RepertoireEntry, RepertoireEntry.id == PracticePlan.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id, PracticePlan.repertoire_entry_id == entry_id)
            .order_by(PracticePlan.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def advance_step(self, user: User, plan_id: uuid.UUID, step_id: uuid.UUID) -> PracticePlan:
        plan = await self.get(user, plan_id)
        step = next((s for s in plan.steps if s.id == step_id), None)
        if step is None:
            raise LookupError("plan step not found")
        step.advance()
        if step.is_done:
            nxt = next((s for s in plan.steps if s.status == PlanStepStatus.TODO), None)
            if nxt is not None:
                nxt.status = PlanStepStatus.ACTIVE
        await self.session.flush()
        return await self.get(user, plan.id)


class SightReadingGenerator(BaseService):
    async def generate(
        self,
        user: User,
        style_composer_id: Optional[int] = None,
        target_piece_id: Optional[int] = None,
        technique_id: Optional[int] = None,
        difficulty: Optional[float] = None,
    ) -> SightReadingExercise:
        if difficulty is None:
            difficulty = await self.suggested_difficulty(user)
        seed = random.getrandbits(48)
        category = None
        technique_name = None
        if technique_id is not None:
            technique = await self.session.get(Technique, technique_id)
            category = technique.category.value if technique else None
            technique_name = technique.name if technique else None
        notation = SightReadingForge(seed).generate(category, difficulty, technique_name)
        exercise = SightReadingExercise(
            user_id=user.id,
            style_composer_id=style_composer_id,
            target_piece_id=target_piece_id,
            technique_id=technique_id,
            difficulty=Decimal(str(round(difficulty, 1))),
            seed=seed,
            notation=notation,
        )
        self.session.add(exercise)
        await self.session.flush()
        return await self.get(user, exercise.id)

    async def suggested_difficulty(self, user: User) -> float:
        stmt = (
            select(func.avg(Piece.difficulty_score))
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .where(RepertoireEntry.user_id == user.id)
        )
        average = (await self.session.execute(stmt)).scalar_one_or_none()
        base = float(average) / 10.0 if average is not None else 4.0
        return max(1.0, min(10.0, round(base - 2.0, 1)))

    @staticmethod
    def exercise_options():
        return (
            selectinload(SightReadingExercise.style_composer),
            selectinload(SightReadingExercise.target_piece),
            selectinload(SightReadingExercise.technique),
        )

    async def get(self, user: User, exercise_id: uuid.UUID) -> SightReadingExercise:
        stmt = (
            select(SightReadingExercise)
            .options(*self.exercise_options())
            .where(SightReadingExercise.id == exercise_id, SightReadingExercise.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        exercise = result.scalar_one_or_none()
        if exercise is None:
            raise LookupError("exercise not found")
        return exercise

    async def list(self, user: User, limit: int = 30) -> list[SightReadingExercise]:
        stmt = (
            select(SightReadingExercise)
            .options(*self.exercise_options())
            .where(SightReadingExercise.user_id == user.id)
            .order_by(SightReadingExercise.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def score(self, user: User, exercise_id: uuid.UUID, self_score: int) -> SightReadingExercise:
        from datetime import datetime, timezone

        exercise = await self.get(user, exercise_id)
        exercise.self_score = self_score
        exercise.attempted_at = datetime.now(timezone.utc)
        if exercise.technique_id is not None and self_score >= 4:
            await self.prove_mastery(user, exercise.technique_id)
        await self.session.flush()
        return exercise

    async def prove_mastery(self, user: User, technique_id: int) -> UserTechniqueProfile:
        profile = await self.session.get(UserTechniqueProfile, (user.id, technique_id))
        if profile is None:
            profile = UserTechniqueProfile(
                user_id=user.id,
                technique_id=technique_id,
                self_rating=SelfRating.STRENGTH,
                proficiency_score=Decimal("8.5"),
            )
            self.session.add(profile)
        else:
            profile.self_rating = SelfRating.STRENGTH
            current = profile.proficiency_score or Decimal("0")
            profile.proficiency_score = max(current, Decimal("8.5"))
        await self.session.flush()
        return profile


class PolyrhythmTrainer(BaseService):
    async def record(
        self,
        user: User,
        ratio_left: int,
        ratio_right: int,
        bpm: int,
        offsets_ms: Sequence[float],
    ) -> PolyrhythmAttempt:
        mean_offset = sum(offsets_ms) / len(offsets_ms) if offsets_ms else None
        accuracy = self.accuracy_from(offsets_ms, bpm)
        attempt = PolyrhythmAttempt(
            user_id=user.id,
            ratio_left=ratio_left,
            ratio_right=ratio_right,
            bpm=bpm,
            mean_offset_ms=Decimal(str(round(mean_offset, 2))) if mean_offset is not None else None,
            accuracy_score=Decimal(str(accuracy)) if accuracy is not None else None,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    @staticmethod
    def accuracy_from(offsets_ms: Sequence[float], bpm: int) -> Optional[float]:
        if not offsets_ms:
            return None
        beat_ms = 60000.0 / max(bpm, 1)
        tolerance = beat_ms * 0.25
        errors = [min(abs(offset) / tolerance, 1.0) for offset in offsets_ms]
        return round(max(0.0, 1.0 - sum(errors) / len(errors)), 3)

    async def list(self, user: User, limit: int = 50) -> list[PolyrhythmAttempt]:
        stmt = (
            select(PolyrhythmAttempt)
            .where(PolyrhythmAttempt.user_id == user.id)
            .order_by(PolyrhythmAttempt.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def stats(self, user: User) -> dict:
        stmt = (
            select(
                PolyrhythmAttempt.ratio_left,
                PolyrhythmAttempt.ratio_right,
                func.count(),
                func.avg(PolyrhythmAttempt.accuracy_score),
                func.max(PolyrhythmAttempt.bpm),
            )
            .where(PolyrhythmAttempt.user_id == user.id)
            .group_by(PolyrhythmAttempt.ratio_left, PolyrhythmAttempt.ratio_right)
        )
        rows = (await self.session.execute(stmt)).all()
        return {
            "ratios": [
                {
                    "ratio": f"{left}:{right}",
                    "attempts": int(count),
                    "average_accuracy": round(float(avg), 3) if avg is not None else None,
                    "best_bpm": int(best) if best is not None else None,
                }
                for left, right, count, avg, best in rows
            ]
        }

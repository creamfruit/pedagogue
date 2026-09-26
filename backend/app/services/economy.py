from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Achievement,
    Cosmetic,
    CosmeticKind,
    GRADED_PASS_SCORE,
    LedgerEntry,
    LedgerReason,
    Piece,
    PolyrhythmAttempt,
    ReadinessScore,
    RepertoireEntry,
    RepertoireStatus,
    Submission,
    User,
    UserAchievement,
    UserCosmetic,
    Wallet,
)
from app.services.onboarding import BaseService
from app.services.streaks import StreakService

LEARNED_STATUSES = {RepertoireStatus.PERFORMANCE_READY, RepertoireStatus.RETIRED}

XP_PER_DIFFICULTY = 42
GOLD_PER_DIFFICULTY = 13
XP_PER_PRACTICE_MINUTE = 2
GOLD_PER_PRACTICE_MINUTE = 1
PRACTICE_MINUTE_CAP = 120
GRADED_GOLD_BASE = 130
GRADED_GOLD_PER_POINT = 14
GRADED_XP_BASE = 180
PATHWAY_XP_PER_STEP = 25


@dataclass(frozen=True)
class AchievementRule:
    metric: str
    target: float
    template: str
    percent: bool = False

    def describe(self, current: float) -> str:
        scale = 100 if self.percent else 1
        return self.template.format(
            current=f"{round(min(current, self.target) * scale):g}" if "{current}" in self.template else "",
            best=f"{round(current * scale):g}",
            target=f"{round(self.target * scale):g}",
        )


ACHIEVEMENT_RULES: dict[str, AchievementRule] = {
    "first_piece": AchievementRule("repertoire", 1, "{current} of {target} pieces added"),
    "first_learned": AchievementRule("learned", 1, "{current} of {target} pieces learnt"),
    "five_learned": AchievementRule("learned", 5, "{current} of {target} pieces learnt"),
    "twenty_learned": AchievementRule("learned", 20, "{current} of {target} pieces learnt"),
    "first_submission": AchievementRule("submissions", 1, "{current} of {target} submissions"),
    "first_pass": AchievementRule("best_grade", 80, "best graded run {best}, needs {target}"),
    "grade_ninety": AchievementRule("best_grade", 90, "best graded run {best}, needs {target}"),
    "flawless": AchievementRule("best_grade", 98, "best graded run {best}, needs {target}"),
    "five_graded": AchievementRule("graded_cleared", 5, "{current} of {target} pieces cleared at 80+"),
    "grade_eight_club": AchievementRule("hardest_learned", 80, "hardest piece learnt {best}, needs {target}"),
    "virtuoso": AchievementRule("hardest_learned", 95, "hardest piece learnt {best}, needs {target}"),
    "polyrhythm_steady": AchievementRule("best_polyrhythm", 0.9, "best polyrhythm {best}%, needs {target}%", percent=True),
    "level_five": AchievementRule("level", 5, "level {best} of {target}"),
    "level_ten": AchievementRule("level", 10, "level {best} of {target}"),
    "first_fortune": AchievementRule("lifetime_gold", 1000, "{current} of {target} gold earned"),
    "streak_three": AchievementRule("longest_streak", 3, "longest streak {best} of {target} days"),
    "streak_week": AchievementRule("longest_streak", 7, "longest streak {best} of {target} days"),
    "streak_month": AchievementRule("longest_streak", 30, "longest streak {best} of {target} days"),
}

ACHIEVEMENT_SERIES: dict[str, list[str]] = {
    "repertoire": ["first_piece", "first_learned", "five_learned", "twenty_learned"],
    "grading": ["first_pass", "grade_ninety", "flawless"],
    "cleared": ["five_graded"],
    "difficulty": ["grade_eight_club", "virtuoso"],
    "streak": ["streak_three", "streak_week", "streak_month"],
    "level": ["level_five", "level_ten"],
    "submissions": ["first_submission"],
    "polyrhythm": ["polyrhythm_steady"],
    "gold": ["first_fortune"],
}

SERIES_OF = {code: (series, index + 1) for series, codes in ACHIEVEMENT_SERIES.items() for index, code in enumerate(codes)}


def learning_reward(difficulty: Optional[Decimal]) -> tuple[int, int]:
    value = float(difficulty) / 10.0 if difficulty is not None else 4.0
    return round(value * XP_PER_DIFFICULTY), round(value * GOLD_PER_DIFFICULTY)


def graded_reward(difficulty: Optional[Decimal], score: Decimal) -> tuple[int, int]:
    value = float(difficulty) / 10.0 if difficulty is not None else 7.0
    over = max(float(score) - float(GRADED_PASS_SCORE), 0.0)
    gold = round(value * GRADED_GOLD_BASE / 10 + over * GRADED_GOLD_PER_POINT + value * 20)
    xp = round(GRADED_XP_BASE + value * 30 + over * 8)
    return xp, gold


def practice_reward(minutes: int) -> tuple[int, int]:
    capped = min(max(minutes, 0), PRACTICE_MINUTE_CAP)
    return capped * XP_PER_PRACTICE_MINUTE, capped * GOLD_PER_PRACTICE_MINUTE


class EconomyService(BaseService):
    async def wallet(self, user: User) -> Wallet:
        wallet = await self.session.get(Wallet, user.id)
        if wallet is None:
            wallet = Wallet(user_id=user.id)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def award(
        self,
        user: User,
        xp: int,
        gold: int,
        reason: LedgerReason,
        detail: Optional[str] = None,
        ref_type: Optional[str] = None,
        ref_id: Optional[str] = None,
    ) -> LedgerEntry:
        wallet = await self.wallet(user)
        wallet.xp += max(xp, 0)
        wallet.gold += max(gold, 0)
        wallet.lifetime_xp += max(xp, 0)
        wallet.lifetime_gold += max(gold, 0)
        entry = LedgerEntry(
            user_id=user.id,
            delta_xp=xp,
            delta_gold=gold,
            reason=reason,
            detail=detail,
            ref_type=ref_type,
            ref_id=str(ref_id) if ref_id is not None else None,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def spend(self, user: User, gold: int, detail: str, ref_id: Optional[str] = None) -> LedgerEntry:
        wallet = await self.wallet(user)
        if wallet.gold < gold:
            raise ValueError(f"not enough gold: you have {wallet.gold}, this costs {gold}")
        wallet.gold -= gold
        entry = LedgerEntry(
            user_id=user.id,
            delta_xp=0,
            delta_gold=-gold,
            reason=LedgerReason.PURCHASE,
            detail=detail,
            ref_type="cosmetic",
            ref_id=str(ref_id) if ref_id is not None else None,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def ledger(self, user: User, limit: int = 40) -> list[LedgerEntry]:
        stmt = (
            select(LedgerEntry)
            .where(LedgerEntry.user_id == user.id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def reward_learning(self, user: User, entry: RepertoireEntry) -> Optional[LedgerEntry]:
        already = await self.session.execute(
            select(LedgerEntry).where(
                LedgerEntry.user_id == user.id,
                LedgerEntry.reason == LedgerReason.PIECE_LEARNED,
                LedgerEntry.ref_id == str(entry.id),
            )
        )
        if already.scalar_one_or_none() is not None:
            return None
        xp, gold = learning_reward(entry.piece.difficulty_score)
        return await self.award(
            user,
            xp,
            gold,
            LedgerReason.PIECE_LEARNED,
            detail=f"learned {entry.piece.title}",
            ref_type="repertoire_entry",
            ref_id=entry.id,
        )

    async def reward_graded(self, user: User, entry: RepertoireEntry, score: ReadinessScore) -> LedgerEntry:
        xp, gold = graded_reward(entry.piece.difficulty_score, score.overall_score)
        return await self.award(
            user,
            xp,
            gold,
            LedgerReason.GRADED_PERFORMANCE,
            detail=f"graded {score.overall_score} on {entry.piece.title}",
            ref_type="readiness_score",
            ref_id=score.id,
        )

    async def reward_practice(self, user: User, minutes: int, session_id) -> Optional[LedgerEntry]:
        if minutes <= 0:
            return None
        xp, gold = practice_reward(minutes)
        return await self.award(
            user,
            xp,
            gold,
            LedgerReason.PRACTICE_SESSION,
            detail=f"{minutes} minutes practised",
            ref_type="practice_session",
            ref_id=session_id,
        )


class AchievementEngine(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.economy = EconomyService(session)

    async def earned_codes(self, user: User) -> set[str]:
        stmt = (
            select(Achievement.code)
            .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
            .where(UserAchievement.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def count(self, model, *conditions) -> int:
        stmt = select(func.count()).select_from(model).where(*conditions)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def metrics(self, user: User) -> dict:
        learned = await self.count(
            RepertoireEntry,
            RepertoireEntry.user_id == user.id,
            RepertoireEntry.status.in_(list(LEARNED_STATUSES)),
        )
        total = await self.count(RepertoireEntry, RepertoireEntry.user_id == user.id)
        submissions = await self.session.execute(
            select(func.count())
            .select_from(Submission)
            .join(RepertoireEntry, RepertoireEntry.id == Submission.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id)
        )
        best_grade = await self.session.execute(
            select(func.max(ReadinessScore.overall_score))
            .join(RepertoireEntry, RepertoireEntry.id == ReadinessScore.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id)
        )
        hardest = await self.session.execute(
            select(func.max(Piece.difficulty_score))
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .where(
                RepertoireEntry.user_id == user.id,
                RepertoireEntry.status.in_(list(LEARNED_STATUSES)),
            )
        )
        polyrhythm = await self.session.execute(
            select(func.max(PolyrhythmAttempt.accuracy_score)).where(PolyrhythmAttempt.user_id == user.id)
        )
        cleared = await self.session.execute(
            select(func.count(func.distinct(ReadinessScore.repertoire_entry_id)))
            .join(RepertoireEntry, RepertoireEntry.id == ReadinessScore.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id, ReadinessScore.overall_score >= GRADED_PASS_SCORE)
        )
        streak = await StreakService(self.session).stats(user)
        wallet = await self.economy.wallet(user)
        return {
            "graded_cleared": int(cleared.scalar_one() or 0),
            "longest_streak": streak.longest,
            "learned": learned,
            "repertoire": total,
            "submissions": int(submissions.scalar_one()),
            "best_grade": float(best_grade.scalar_one_or_none() or 0),
            "hardest_learned": float(hardest.scalar_one_or_none() or 0),
            "best_polyrhythm": float(polyrhythm.scalar_one_or_none() or 0),
            "level": wallet.level,
            "lifetime_gold": wallet.lifetime_gold,
        }

    @staticmethod
    def qualifies(code: str, metrics: dict) -> bool:
        rule = ACHIEVEMENT_RULES.get(code)
        return rule is not None and metrics.get(rule.metric, 0) >= rule.target

    @staticmethod
    def progress(code: str, metrics: dict) -> Optional[dict]:
        rule = ACHIEVEMENT_RULES.get(code)
        if rule is None:
            return None
        current = float(metrics.get(rule.metric, 0))
        fraction = 1.0 if rule.target <= 0 else max(0.0, min(current / rule.target, 1.0))
        return {"current": current, "target": float(rule.target), "fraction": round(fraction, 3), "label": rule.describe(current)}

    async def evaluate(self, user: User) -> list[Achievement]:
        metrics = await self.metrics(user)
        earned = await self.earned_codes(user)
        catalog = (await self.session.execute(select(Achievement).order_by(Achievement.sort_order))).scalars().all()
        unlocked: list[Achievement] = []
        for achievement in catalog:
            if achievement.code in earned:
                continue
            if not self.qualifies(achievement.code, metrics):
                continue
            self.session.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
            await self.session.flush()
            await self.economy.award(
                user,
                achievement.xp_reward,
                achievement.gold_reward,
                LedgerReason.ACHIEVEMENT,
                detail=achievement.name,
                ref_type="achievement",
                ref_id=achievement.id,
            )
            unlocked.append(achievement)
        return unlocked

    async def list_for(self, user: User) -> list[dict]:
        catalog = (await self.session.execute(select(Achievement).order_by(Achievement.sort_order))).scalars().all()
        earned = await self.session.execute(
            select(UserAchievement).where(UserAchievement.user_id == user.id)
        )
        earned_map = {row.achievement_id: row.earned_at for row in earned.scalars().all()}
        metrics = await self.metrics(user)
        return [
            {
                "series": SERIES_OF.get(achievement.code, (None, None))[0],
                "tier": SERIES_OF.get(achievement.code, (None, None))[1],
                "progress": self.progress(achievement.code, metrics),
                "id": achievement.id,
                "code": achievement.code,
                "name": achievement.name,
                "description": achievement.description,
                "xp_reward": achievement.xp_reward,
                "gold_reward": achievement.gold_reward,
                "earned": achievement.id in earned_map,
                "earned_at": earned_map.get(achievement.id),
            }
            for achievement in catalog
        ]


class CosmeticService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.economy = EconomyService(session)

    async def _all(self) -> list[Cosmetic]:
        result = await self.session.execute(
            select(Cosmetic).order_by(Cosmetic.kind, Cosmetic.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    def _defaults(cosmetics: Sequence[Cosmetic]) -> dict[CosmeticKind, Cosmetic]:
        defaults: dict[CosmeticKind, Cosmetic] = {}
        for item in cosmetics:
            if item.price_gold == 0 and item.kind not in defaults:
                defaults[item.kind] = item
        return defaults

    async def catalog(self, user: User) -> list[dict]:
        cosmetics = await self._all()
        owned = await self.session.execute(
            select(UserCosmetic).where(UserCosmetic.user_id == user.id)
        )
        owned_map = {row.cosmetic_id: row for row in owned.scalars().all()}
        equipped_kinds = {
            item.kind
            for item in cosmetics
            if owned_map.get(item.id) and owned_map[item.id].equipped
        }
        defaults = self._defaults(cosmetics)
        wallet = await self.economy.wallet(user)
        return [
            {
                "id": item.id,
                "code": item.code,
                "kind": item.kind,
                "name": item.name,
                "description": item.description,
                "price_gold": item.price_gold,
                "min_level": item.min_level,
                "payload": item.payload,
                "owned": item.id in owned_map or item.price_gold == 0,
                "equipped": bool(owned_map.get(item.id) and owned_map[item.id].equipped)
                or (item.kind not in equipped_kinds and defaults.get(item.kind) is item),
                "affordable": wallet.gold >= item.price_gold,
                "unlocked": wallet.level >= item.min_level,
            }
            for item in cosmetics
        ]

    async def purchase(self, user: User, cosmetic_id: int) -> UserCosmetic:
        cosmetic = await self.session.get(Cosmetic, cosmetic_id)
        if cosmetic is None:
            raise LookupError("cosmetic not found")
        wallet = await self.economy.wallet(user)
        if wallet.level < cosmetic.min_level:
            raise ValueError(f"reach level {cosmetic.min_level} to unlock {cosmetic.name}")
        existing = await self.session.get(UserCosmetic, (user.id, cosmetic_id))
        if existing is not None:
            raise ValueError("you already own that")
        if cosmetic.price_gold > 0:
            await self.economy.spend(user, cosmetic.price_gold, f"bought {cosmetic.name}", cosmetic.id)
        owned = UserCosmetic(user_id=user.id, cosmetic_id=cosmetic_id)
        self.session.add(owned)
        await self.session.flush()
        return owned

    async def equip(self, user: User, cosmetic_id: int) -> UserCosmetic:
        cosmetic = await self.session.get(Cosmetic, cosmetic_id)
        if cosmetic is None:
            raise LookupError("cosmetic not found")
        owned = await self.session.get(UserCosmetic, (user.id, cosmetic_id))
        if owned is None:
            if cosmetic.price_gold > 0:
                raise ValueError("buy it before equipping it")
            owned = UserCosmetic(user_id=user.id, cosmetic_id=cosmetic_id)
            self.session.add(owned)
            await self.session.flush()

        siblings = await self.session.execute(
            select(UserCosmetic)
            .join(Cosmetic, Cosmetic.id == UserCosmetic.cosmetic_id)
            .where(UserCosmetic.user_id == user.id, Cosmetic.kind == cosmetic.kind)
        )
        for row in siblings.scalars().all():
            row.equipped = row.cosmetic_id == cosmetic_id
        owned.equipped = True
        await self.session.flush()
        return owned

    async def loadout(self, user: User) -> dict:
        stmt = (
            select(Cosmetic)
            .join(UserCosmetic, UserCosmetic.cosmetic_id == Cosmetic.id)
            .where(UserCosmetic.user_id == user.id, UserCosmetic.equipped.is_(True))
        )
        result = await self.session.execute(stmt)
        loadout: dict[str, Optional[dict]] = {kind.value: None for kind in CosmeticKind}
        for cosmetic in result.scalars().all():
            loadout[cosmetic.kind.value] = {
                "code": cosmetic.code,
                "name": cosmetic.name,
                "payload": cosmetic.payload or {},
            }
        defaults = self._defaults(await self._all())
        for kind, cosmetic in defaults.items():
            if loadout.get(kind.value) is None:
                loadout[kind.value] = {
                    "code": cosmetic.code,
                    "name": cosmetic.name,
                    "payload": cosmetic.payload or {},
                }
        return loadout

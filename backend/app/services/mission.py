from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import (
    Mission,
    Passage,
    PracticeMode,
    PracticeSession,
    Piece,
    RepertoireEntry,
    RepertoireStatus,
    SelfRating,
    SessionItem,
    User,
    UserTechniqueProfile,
    Wallet,
)
from app.services.onboarding import BaseService
from app.services.practice import PracticeSessionService
from app.services.streaks import StreakService, zone_for

ACTIVE_STATUSES = (RepertoireStatus.LEARNING, RepertoireStatus.POLISHING)
REVIEWABLE_STATUSES = (RepertoireStatus.LEARNING, RepertoireStatus.POLISHING, RepertoireStatus.PERFORMANCE_READY)

DAILY_MINUTES = {"warmup": 2, "passage": 5, "review": 3, "playthrough": 4}
FIRST_MINUTES = {"warmup": 1, "passage": 2, "playthrough": 2}
NO_PIECES_MINUTES = {"warmup": 4, "freeplay": 6}
WEAK_BELOW = 6.5
STRUGGLE_SCORE = 3.0
STRENGTH_SCORE = 8.5
MAX_STEP_MINUTES = 30
MIN_TAP_SECONDS = 1


@dataclass
class PassageInfo:
    id: int
    start: int
    end: int
    label: Optional[str]
    difficulty: float
    cue: Optional[str] = None
    score_crop: Optional[str] = None

    @property
    def bars(self) -> str:
        return f"bar {self.start}" if self.start == self.end else f"bars {self.start}-{self.end}"


@dataclass
class EntryInfo:
    id: str
    piece_id: int
    title: str
    composer: Optional[str]
    status: str
    difficulty: float
    decay: float
    days_ago: Optional[float]
    current_tempo: Optional[int]
    target_tempo: Optional[int]
    passages: list[PassageInfo] = field(default_factory=list)
    techniques: list[int] = field(default_factory=list)

    @property
    def progress(self) -> float:
        if not self.current_tempo or not self.target_tempo:
            return 0.5
        return min(self.current_tempo / self.target_tempo, 1.0)


@dataclass
class TechniqueInfo:
    id: int
    name: str
    mechanic: Optional[str]
    score: Optional[float]


@dataclass
class MissionInputs:
    entries: list[EntryInfo]
    techniques: list[TechniqueInfo]
    day: date
    seed: str
    avoid_passages: set[int] = field(default_factory=set)
    avoid_technique: Optional[int] = None
    first: bool = False


def jitter(seed: str, key: str) -> float:
    digest = hashlib.sha1(f"{seed}:{key}".encode()).digest()
    return (int.from_bytes(digest[:2], "big") % 1000) / 10000.0


def age_phrase(days: Optional[float]) -> str:
    if days is None:
        return "not yet played"
    whole = int(days)
    if whole <= 0:
        return "played earlier today"
    if whole == 1:
        return "last played yesterday"
    return f"last played {whole} days ago"


def technique_score(rating: SelfRating, proficiency: Optional[Decimal]) -> Optional[float]:
    if proficiency is not None:
        return float(proficiency)
    if rating == SelfRating.STRUGGLE:
        return STRUGGLE_SCORE
    if rating == SelfRating.STRENGTH:
        return STRENGTH_SCORE
    return None


def pick_technique(inputs: MissionInputs, pool: list[EntryInfo]) -> Optional[TechniqueInfo]:
    counts: dict[int, int] = {}
    for entry in pool:
        for technique_id in entry.techniques:
            counts[technique_id] = counts.get(technique_id, 0) + 1
    rated = [item for item in inputs.techniques if item.score is not None and item.score < WEAK_BELOW]
    related = [item for item in rated if counts.get(item.id)]
    ranked = sorted(related or rated, key=lambda item: (item.score, -counts.get(item.id, 0), item.name))
    fresh = [item for item in ranked if item.id != inputs.avoid_technique]
    if fresh:
        return fresh[0]
    by_id = {item.id: item for item in inputs.techniques}
    common = sorted(counts, key=lambda technique_id: (-counts[technique_id], by_id[technique_id].name if technique_id in by_id else ""))
    common = [technique_id for technique_id in common if technique_id in by_id]
    fresh_common = [technique_id for technique_id in common if technique_id != inputs.avoid_technique]
    if fresh_common:
        return by_id[fresh_common[0]]
    if ranked:
        return ranked[0]
    return by_id[common[0]] if common else None


def suggested_tempo(entry: Optional[EntryInfo], factor: float, fallback: int) -> int:
    if entry is None:
        return fallback
    base = entry.current_tempo or (round(entry.target_tempo * 0.7) if entry.target_tempo else None)
    if not base:
        return fallback
    return max(40, min(round(base * factor), 180))


def base_step(kind: str, minutes: int, why: str, title: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "minutes": minutes,
        "why": why,
        "entry_id": None,
        "piece_id": None,
        "piece_title": None,
        "composer": None,
        "passage_id": None,
        "bars": None,
        "start_measure": None,
        "end_measure": None,
        "technique_id": None,
        "technique": None,
        "mechanic": None,
        "cue": None,
        "tempo_bpm": 72,
        "star_entry_id": None,
    }


def with_entry(step: dict[str, Any], entry: EntryInfo, passage: Optional[PassageInfo] = None) -> dict[str, Any]:
    step.update(entry_id=entry.id, piece_id=entry.piece_id, piece_title=entry.title, composer=entry.composer, star_entry_id=entry.id)
    if passage is not None:
        step.update(passage_id=passage.id, bars=passage.bars, start_measure=passage.start, end_measure=passage.end, cue=passage.cue)
    return step


def warmup_step(inputs: MissionInputs, pool: list[EntryInfo], minutes: int) -> dict[str, Any]:
    technique = pick_technique(inputs, pool)
    if technique is None:
        step = base_step("warmup", minutes, "A slow, even pattern to wake your hands up before the real work.", "Warm up")
        step["mechanic"] = "Five-finger patterns, hands separate, even and relaxed. Listen for every note sounding the same."
        step["cue"] = step["mechanic"]
        anchor = pool[0] if pool else None
        if anchor is not None:
            step["star_entry_id"] = anchor.id
        return step
    related = [entry for entry in pool if technique.id in entry.techniques]
    weak = technique.score is not None and technique.score < WEAK_BELOW
    if weak:
        why = f"{technique.name} is one of your lowest-rated techniques, so we start there."
    else:
        why = f"{technique.name} turns up in your pieces, so your hands meet it before the music does."
    step = base_step("warmup", minutes, why, f"Warm up: {technique.name}")
    step.update(technique_id=technique.id, technique=technique.name, mechanic=technique.mechanic, cue=technique.mechanic)
    anchor = related[0] if related else (pool[0] if pool else None)
    if anchor is not None:
        step["star_entry_id"] = anchor.id
    step["tempo_bpm"] = 72
    return step


def passage_candidates(pool: list[EntryInfo], avoid: set[int]) -> list[tuple[EntryInfo, PassageInfo]]:
    return [(entry, passage) for entry in pool for passage in entry.passages if passage.id not in avoid]


def passage_step(inputs: MissionInputs, pool: list[EntryInfo], minutes: int) -> tuple[dict[str, Any], Optional[EntryInfo], Optional[PassageInfo]]:
    candidates = passage_candidates(pool, inputs.avoid_passages)

    def score(pair: tuple[EntryInfo, PassageInfo]) -> float:
        entry, passage = pair
        stale = 0.4 if entry.days_ago is None else min(entry.days_ago, 14) / 14 * 0.4
        return passage.difficulty * (0.6 + 0.8 * entry.decay + stale) + jitter(inputs.seed, f"p{passage.id}")

    if candidates:
        entry, passage = max(candidates, key=score)
        label = f"{passage.label} ({passage.bars})" if passage.label else passage.bars
        if entry.decay >= 0.35:
            why = f"{label} in {entry.title} is your hardest section, and the piece is drifting."
        else:
            why = f"{label} in {entry.title} is the hardest section you haven't touched lately."
        step = with_entry(base_step("passage", minutes, why, f"Hardest passage: {entry.title}"), entry, passage)
        step["tempo_bpm"] = suggested_tempo(entry, 0.8, 60)
        return step, entry, passage
    ranked = sorted(pool, key=lambda item: -(item.difficulty * (0.6 + 0.8 * item.decay) + jitter(inputs.seed, f"e{item.id}")))
    entry = ranked[0]
    why = f"{entry.title} has no marked passages yet, so work its trickiest page slowly."
    step = with_entry(base_step("passage", minutes, why, f"Slow work: {entry.title}"), entry)
    step["tempo_bpm"] = suggested_tempo(entry, 0.7, 56)
    return step, entry, None


def review_step(
    inputs: MissionInputs, pool: list[EntryInfo], minutes: int, used_entry: Optional[EntryInfo], used_passage: Optional[PassageInfo]
) -> tuple[dict[str, Any], EntryInfo]:
    others = [entry for entry in pool if used_entry is None or entry.id != used_entry.id]
    if others:
        seen = [entry for entry in others if entry.days_ago is not None]
        ranked = sorted(seen or others, key=lambda item: (-item.decay, -(item.days_ago or 0), item.title))
        entry = ranked[0]
        if entry.days_ago is None:
            why = f"{entry.title} hasn't had a first pass yet, so a gentle look is a good start."
        else:
            why = f"{entry.title} was {age_phrase(entry.days_ago)}, so it's due a quick refresh."
        step = with_entry(base_step("review", minutes, why, f"Review: {entry.title}"), entry)
        step["tempo_bpm"] = suggested_tempo(entry, 0.9, 72)
        return step, entry
    entry = used_entry
    spare = [item for item in entry.passages if used_passage is None or item.id != used_passage.id]
    spare = [item for item in spare if item.id not in inputs.avoid_passages]
    if spare:
        second = max(spare, key=lambda item: item.difficulty + jitter(inputs.seed, f"r{item.id}"))
        why = f"Only one piece in play, so we revisit a different part of {entry.title}: {second.bars}."
        step = with_entry(base_step("review", minutes, why, f"Review: {entry.title}"), entry, second)
        step["tempo_bpm"] = suggested_tempo(entry, 0.85, 64)
        return step, entry
    why = f"Only one piece in play, so play the opening of {entry.title} from memory."
    step = with_entry(base_step("review", minutes, why, f"From memory: {entry.title}"), entry)
    step["tempo_bpm"] = suggested_tempo(entry, 0.85, 64)
    return step, entry


def playthrough_step(inputs: MissionInputs, pool: list[EntryInfo], minutes: int, reviewed: Optional[EntryInfo], drilled: Optional[EntryInfo]) -> dict[str, Any]:
    options = [entry for entry in pool if reviewed is None or entry.id != reviewed.id] or pool
    entry = max(options, key=lambda item: item.progress + jitter(inputs.seed, f"t{item.id}"))
    if drilled is not None and entry.id == drilled.id:
        why = f"Now put {entry.title} back together with a full run, no stopping."
    else:
        why = f"{entry.title} is closest to your target tempo, so run it start to finish."
    step = with_entry(base_step("playthrough", minutes, why, f"Play through: {entry.title}"), entry)
    step["tempo_bpm"] = suggested_tempo(entry, 1.0, 80)
    return step


def build_steps(inputs: MissionInputs) -> list[dict[str, Any]]:
    pool = [entry for entry in inputs.entries]
    if not pool:
        warm = warmup_step(inputs, [], NO_PIECES_MINUTES["warmup"])
        free = base_step("freeplay", NO_PIECES_MINUTES["freeplay"], "You haven't added a piece yet, so play anything you enjoy.", "Free play")
        free["cue"] = "Play whatever you like, or add a piece to learn from the Library tab for a fuller mission."
        free["tempo_bpm"] = 80
        return [warm, free]
    if inputs.first:
        minutes = FIRST_MINUTES
        warm = warmup_step(inputs, pool, minutes["warmup"])
        focus, entry, _ = passage_step(inputs, pool, minutes["passage"])
        play = playthrough_step(inputs, pool, minutes["playthrough"], None, entry)
        return [warm, focus, play]
    minutes = DAILY_MINUTES
    warm = warmup_step(inputs, pool, minutes["warmup"])
    focus, drilled, drilled_passage = passage_step(inputs, pool, minutes["passage"])
    review, reviewed = review_step(inputs, pool, minutes["review"], drilled, drilled_passage)
    play = playthrough_step(inputs, pool, minutes["playthrough"], reviewed if len(pool) > 1 else None, drilled)
    return [warm, focus, review, play]


def number_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, step in enumerate(steps):
        step["index"] = index
    return steps


def step_minutes(seconds: int, planned: int) -> int:
    minutes = max(1, math.ceil(max(seconds, MIN_TAP_SECONDS) / 60))
    return min(minutes, max(planned * 2, 2), MAX_STEP_MINUTES)


class MissionService(BaseService):
    def __init__(self, session) -> None:
        super().__init__(session)

    @staticmethod
    def today_for(user: User) -> date:
        return datetime.now(zone_for(user)).date()

    async def find(self, user: User, day: date) -> Optional[Mission]:
        found = await self.session.execute(select(Mission).where(Mission.user_id == user.id, Mission.day == day))
        return found.scalar_one_or_none()

    async def load_entries(self, user: User) -> list[RepertoireEntry]:
        stmt = (
            select(RepertoireEntry)
            .options(
                selectinload(RepertoireEntry.piece).selectinload(Piece.composer),
                selectinload(RepertoireEntry.piece).selectinload(Piece.technique_links),
                selectinload(RepertoireEntry.piece).selectinload(Piece.passages),
            )
            .where(RepertoireEntry.user_id == user.id, RepertoireEntry.status.in_(REVIEWABLE_STATUSES))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def technique_infos(self, user: User) -> list[TechniqueInfo]:
        stmt = select(UserTechniqueProfile).options(selectinload(UserTechniqueProfile.technique)).where(UserTechniqueProfile.user_id == user.id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            TechniqueInfo(row.technique_id, row.technique.name, row.technique.mechanic or row.technique.description, technique_score(row.self_rating, row.proficiency_score))
            for row in rows
        ]

    async def known_techniques(self, ids: set[int], have: list[TechniqueInfo]) -> list[TechniqueInfo]:
        from app.models.models import Technique

        missing = ids - {item.id for item in have}
        if not missing:
            return have
        rows = (await self.session.execute(select(Technique).where(Technique.id.in_(missing)))).scalars().all()
        return have + [TechniqueInfo(row.id, row.name, row.mechanic or row.description, None) for row in rows]

    async def yesterday_avoidance(self, user: User, today: date) -> tuple[set[int], Optional[int]]:
        yesterday = today - timedelta(days=1)
        previous = await self.find(user, yesterday)
        passages: set[int] = set()
        technique: Optional[int] = None
        if previous is not None:
            for step in previous.steps:
                if step.get("passage_id"):
                    passages.add(int(step["passage_id"]))
                if step.get("kind") == "warmup" and step.get("technique_id"):
                    technique = int(step["technique_id"])
        zone = zone_for(user)
        start = datetime.combine(yesterday, datetime.min.time(), tzinfo=zone).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        stmt = (
            select(SessionItem.passage_id)
            .join(PracticeSession, PracticeSession.id == SessionItem.session_id)
            .where(PracticeSession.user_id == user.id, PracticeSession.started_at >= start, PracticeSession.started_at < end, SessionItem.passage_id.is_not(None))
        )
        passages.update(int(value) for value in (await self.session.execute(stmt)).scalars().all())
        return passages, technique

    def entry_info(self, entry: RepertoireEntry, now: datetime) -> EntryInfo:
        piece = entry.piece
        days = None
        if entry.last_practiced_at is not None:
            days = max((now - entry.last_practiced_at).total_seconds() / 86400, 0.0)
        passages = [
            PassageInfo(
                id=item.id,
                start=item.start_measure,
                end=item.end_measure,
                label=item.label,
                difficulty=float(item.difficulty_score) if item.difficulty_score is not None else 5.0,
                cue=item.practice_cue,
            )
            for item in piece.passages
        ]
        return EntryInfo(
            id=str(entry.id),
            piece_id=piece.id,
            title=piece.display_title,
            composer=piece.composer.name if piece.composer else None,
            status=entry.status.value,
            difficulty=float(piece.difficulty_score) if piece.difficulty_score is not None else 40.0,
            decay=entry.decay_level,
            days_ago=days,
            current_tempo=entry.current_tempo_bpm,
            target_tempo=entry.target_tempo_bpm,
            passages=passages,
            techniques=[link.technique_id for link in piece.technique_links],
        )

    async def build(self, user: User, day: date, first: bool) -> tuple[str, list[dict[str, Any]]]:
        now = datetime.now(timezone.utc)
        entries = await self.load_entries(user)
        active = [entry for entry in entries if entry.status in ACTIVE_STATUSES]
        chosen = active or entries
        infos = [self.entry_info(entry, now) for entry in chosen]
        technique_ids = {technique_id for info in infos for technique_id in info.techniques}
        techniques = await self.known_techniques(technique_ids, await self.technique_infos(user))
        avoid_passages, avoid_technique = await self.yesterday_avoidance(user, day)
        inputs = MissionInputs(
            entries=infos,
            techniques=techniques,
            day=day,
            seed=f"{user.id}:{day.isoformat()}",
            avoid_passages=avoid_passages,
            avoid_technique=avoid_technique,
            first=first and len(infos) > 0,
        )
        steps = number_steps(build_steps(inputs))
        return ("first" if inputs.first else "daily"), steps

    async def today(self, user: User, first: bool = False) -> Mission:
        day = self.today_for(user)
        mission = await self.find(user, day)
        if mission is not None:
            return mission
        kind, steps = await self.build(user, day, first)
        mission = Mission(user_id=user.id, day=day, kind=kind, steps=steps, progress=[])
        self.session.add(mission)
        await self.session.flush()
        return mission

    @staticmethod
    def finished(mission: Mission) -> bool:
        return len(mission.progress) >= len(mission.steps)

    async def ensure_session(self, user: User, mission: Mission) -> PracticeSession:
        service = PracticeSessionService(self.session)
        if mission.session_id is not None:
            existing = await self.session.get(PracticeSession, mission.session_id)
            if existing is not None and existing.ended_at is None:
                return existing
        open_session = await service.open_session(user)
        if open_session is not None:
            mission.session_id = open_session.id
            mission.owns_session = False
            return open_session
        started = await service.start(user, PracticeMode.FREE, "Daily mission")
        mission.session_id = started.id
        mission.owns_session = True
        return started

    async def record_step(self, user: User, mission: Mission, index: int, status: str, seconds: int) -> dict[str, Any]:
        if not 0 <= index < len(mission.steps):
            raise LookupError("that mission has no such step")
        if any(item["index"] == index for item in mission.progress):
            return {"already": True, "minutes": 0}
        step = mission.steps[index]
        minutes = 0
        if status == "done":
            minutes = step_minutes(seconds, int(step.get("minutes") or 1))
            practice = await self.ensure_session(user, mission)
            entry_id = uuid.UUID(step["entry_id"]) if step.get("entry_id") and step["kind"] != "warmup" else None
            await PracticeSessionService(self.session).add_item(
                user,
                practice.id,
                minutes=minutes,
                repertoire_entry_id=entry_id,
                passage_id=step.get("passage_id") if entry_id else None,
            )
        mission.progress = [*mission.progress, {"index": index, "status": status, "seconds": max(seconds, 0), "minutes": minutes}]
        await self.session.flush()
        return {"already": False, "minutes": minutes}

    async def finish(self, user: User, mission: Mission) -> dict[str, Any]:
        if mission.completed_at is not None:
            return {"xp": 0, "gold": 0}
        mission.completed_at = datetime.now(timezone.utc)
        reward = {"xp": 0, "gold": 0}
        if mission.session_id is not None:
            practice = await self.session.get(PracticeSession, mission.session_id)
            if practice is not None and practice.ended_at is None and mission.owns_session:
                before = await self.session.get(Wallet, user.id)
                xp_before = before.xp if before else 0
                gold_before = before.gold if before else 0
                await PracticeSessionService(self.session).close(user, practice.id, None)
                after = await self.session.get(Wallet, user.id)
                if after is not None:
                    await self.session.refresh(after)
                    reward = {"xp": after.xp - xp_before, "gold": after.gold - gold_before}
        await self.session.flush()
        return reward

    async def streak(self, user: User) -> dict[str, Any]:
        return (await StreakService(self.session).stats(user)).as_dict()

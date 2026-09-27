from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.models.models import DailySnippet, RouletteAttempt, User
from app.services.leaderboard import LeaderboardService, roulette_board
from app.services.notation import SightReadingForge
from app.services.onboarding import BaseService

ROTATION = ["dexterity", "leaps", "double_notes", "octaves", "repeated_notes", "trills", "stretches", "voicing"]
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
POINTS_PER_NOTE = 100
SPEED_WINDOW_S = 90
SPEED_POINTS_PER_S = 2
SPEED_BONUS_MIN_CORRECT = 6


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def seed_for(day: date) -> int:
    return int(hashlib.sha256(f"roulette:{day.isoformat()}".encode()).hexdigest()[:12], 16)


def spelled(pitch: str) -> str:
    name = pitch.rstrip("-0123456789")
    return name.replace("#", "♯").replace("b", "♭") if len(name) > 1 else name


def diatonic_step(pitch: str) -> int:
    name = pitch.rstrip("-0123456789")
    octave = int(pitch[len(name):])
    return octave * 7 + LETTERS.index(name[0])


def question_note(measure: dict) -> Optional[str]:
    for note in measure.get("notes", []):
        pitches = note.get("pitches") or ([note["pitch"]] if note.get("pitch") else [])
        if pitches:
            return max(pitches, key=diatonic_step)
    return None


def build_quiz(notation: dict, rng: random.Random) -> list[dict]:
    quiz = []
    for index, measure in enumerate(notation["measures"]):
        pitch = question_note(measure)
        if pitch is None:
            continue
        answer = spelled(pitch)
        letter = LETTERS.index(pitch[0])
        accidental = answer[1:] if len(answer) > 1 else ""
        options = {answer}
        for step in (-1, 1, -2, 2, 3):
            if len(options) >= 4:
                break
            options.add(LETTERS[(letter + step) % 7] + accidental)
        ordered = sorted(options)
        rng.shuffle(ordered)
        quiz.append({"measure": index, "note": 0, "answer": answer, "options": ordered})
    return quiz


def generate_snippet(day: date) -> dict:
    rng = random.Random(seed_for(day))
    category = ROTATION[day.toordinal() % len(ROTATION)]
    difficulty = round(4.5 + rng.random() * 2.5, 1)
    notation = SightReadingForge(seed_for(day)).generate(category, difficulty)
    return {
        "day": day,
        "seed": seed_for(day),
        "category": category,
        "difficulty": difficulty,
        "notation": notation,
        "quiz": build_quiz(notation, rng),
    }


def score_attempt(quiz: list[dict], answers: list[Optional[str]], seconds: float) -> dict:
    correct = sum(1 for question, answer in zip(quiz, answers) if answer == question["answer"])
    speed = 0
    if correct >= min(SPEED_BONUS_MIN_CORRECT, len(quiz)):
        speed = max(0, SPEED_WINDOW_S - math.ceil(seconds)) * SPEED_POINTS_PER_S
    return {"correct": correct, "total": len(quiz), "seconds": round(seconds, 1), "speed_bonus": speed, "score": correct * POINTS_PER_NOTE + speed}


async def ensure_snippet(session: AsyncSession, day: date) -> DailySnippet:
    existing = await session.get(DailySnippet, day)
    if existing is not None:
        return existing
    data = generate_snippet(day)
    await session.execute(insert(DailySnippet).values(**data).on_conflict_do_nothing(index_elements=[DailySnippet.day]))
    await session.flush()
    return await session.get(DailySnippet, day)


async def generate_daily_snippet(day: Optional[str] = None) -> str:
    target = date.fromisoformat(day) if day else utc_today()
    async with session_scope() as session:
        snippet = await ensure_snippet(session, target)
        return snippet.day.isoformat()


def public_snippet(snippet: DailySnippet) -> dict:
    return {
        "day": snippet.day.isoformat(),
        "category": snippet.category,
        "difficulty": float(snippet.difficulty),
        "notation": snippet.notation,
        "questions": [{"measure": q["measure"], "note": q["note"], "options": q["options"]} for q in snippet.quiz],
    }


class RouletteService(BaseService):
    async def today(self, user: User) -> dict:
        snippet = await ensure_snippet(self.session, utc_today())
        attempt = await self.attempt(user, snippet.day)
        return {"snippet": public_snippet(snippet), "attempt": self.attempt_view(attempt, snippet)}

    async def attempt(self, user: User, day: date) -> Optional[RouletteAttempt]:
        return (
            await self.session.execute(select(RouletteAttempt).where(RouletteAttempt.user_id == user.id, RouletteAttempt.day == day))
        ).scalar_one_or_none()

    @staticmethod
    def attempt_view(attempt: Optional[RouletteAttempt], snippet: DailySnippet) -> Optional[dict]:
        if attempt is None:
            return None
        view = {"started_at": attempt.started_at, "finished": attempt.finished_at is not None}
        if attempt.finished_at is not None:
            view.update(attempt.result or {})
            view["answers"] = [q["answer"] for q in snippet.quiz]
            view["given"] = attempt.answers
        return view

    async def start(self, user: User) -> dict:
        snippet = await ensure_snippet(self.session, utc_today())
        await self.session.execute(
            insert(RouletteAttempt)
            .values(day=snippet.day, user_id=user.id, started_at=datetime.now(timezone.utc))
            .on_conflict_do_nothing(index_elements=[RouletteAttempt.day, RouletteAttempt.user_id])
        )
        await self.session.flush()
        attempt = await self.attempt(user, snippet.day)
        return {"snippet": public_snippet(snippet), "attempt": self.attempt_view(attempt, snippet)}

    async def submit(self, user: User, answers: list[Optional[str]]) -> dict:
        snippet = await ensure_snippet(self.session, utc_today())
        attempt = await self.attempt(user, snippet.day)
        if attempt is None:
            raise LookupError("start today's roulette first")
        if attempt.finished_at is not None:
            raise ValueError("you've already played today's roulette")
        now = datetime.now(timezone.utc)
        seconds = (now - attempt.started_at).total_seconds()
        result = score_attempt(snippet.quiz, answers, seconds)
        attempt.finished_at = now
        attempt.answers = list(answers)
        attempt.result = result
        attempt.score = result["score"]
        await self.session.flush()
        await LeaderboardService(self.session).submit(
            roulette_board(snippet.day), user, result["score"], {k: result[k] for k in ("correct", "total", "seconds")}, keep="max"
        )
        return self.attempt_view(attempt, snippet)


async def snippet_scheduler() -> None:
    import asyncio
    import logging

    logger = logging.getLogger("piano.roulette")
    while True:
        try:
            await generate_daily_snippet()
        except Exception:
            logger.exception("daily snippet generation failed")
        now = datetime.now(timezone.utc)
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), timezone.utc)
        await asyncio.sleep(max((tomorrow - now).total_seconds() + 5, 60))

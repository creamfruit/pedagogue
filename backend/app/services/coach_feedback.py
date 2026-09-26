from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import session_scope
from app.models.models import (
    AIGeneration,
    AudioSubmission,
    GenerationStatus,
    Passage,
    PassageTechnique,
    Piece,
    PieceTechnique,
    ProcessingStatus,
    RepertoireEntry,
    Submission,
    TextSubmission,
    UserTechniqueProfile,
)
from app.services import ai

logger = logging.getLogger("piano.coach")

PURPOSE = "coach_feedback"
HEURISTIC_MODEL = "heuristic-coach-0.1"
TIER_BY_SCORE = ((Decimal("8.5"), "S"), (Decimal("6.5"), "A"), (Decimal("4.5"), "B"), (Decimal("2.5"), "C"))

SYSTEM = (
    "You are a piano teacher writing short, specific practice notes after a student uploads a recording. "
    "You cannot hear the recording: nothing in the data describes how it sounded, so never comment on the "
    "sound, accuracy, tone, or musicality of this take. Base every note on the piece's marked passages, the "
    "student's own technique tiers and practice notes, and any tempo data provided. Be concrete: name bars, "
    "the technique, and a drill. Write to the student in the second person, warmly and without flattery."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "focus": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "passage": {"type": "string"},
                    "why": {"type": "string"},
                    "drill": {"type": "string"},
                },
                "required": ["passage", "why", "drill"],
                "additionalProperties": False,
            },
        },
        "next_session": {"type": "string"},
    },
    "required": ["summary", "focus", "next_session"],
    "additionalProperties": False,
}


def subject_key(submission_id: uuid.UUID) -> str:
    return f"submission:{submission_id}"


def tier_for(score: Optional[Decimal]) -> Optional[str]:
    if score is None:
        return None
    for floor, tier in TIER_BY_SCORE:
        if score >= floor:
            return tier
    return "D"


async def gather_context(session: AsyncSession, submission: AudioSubmission) -> dict:
    entry = await session.get(RepertoireEntry, submission.repertoire_entry_id)
    piece = (
        await session.execute(
            select(Piece)
            .options(
                selectinload(Piece.composer),
                selectinload(Piece.technique_links).selectinload(PieceTechnique.technique),
                selectinload(Piece.passages).selectinload(Passage.technique_links).selectinload(PassageTechnique.technique),
            )
            .where(Piece.id == entry.piece_id)
        )
    ).scalars().one()
    profiles = {
        profile.technique_id: profile
        for profile in (
            await session.execute(select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == entry.user_id))
        ).scalars().all()
    }
    notes = (
        await session.execute(
            select(TextSubmission)
            .where(TextSubmission.repertoire_entry_id == entry.id)
            .order_by(TextSubmission.created_at.desc())
            .limit(3)
        )
    ).scalars().all()

    techniques = [
        {
            "name": link.technique.name,
            "share": float(link.weight),
            "your_tier": tier_for(profiles[link.technique_id].proficiency_score) if link.technique_id in profiles else None,
        }
        for link in sorted(piece.technique_links, key=lambda link: float(link.weight), reverse=True)
    ]
    passages = [
        {
            "bars": passage.measure_span,
            "label": passage.label,
            "difficulty": float(passage.difficulty_score) if passage.difficulty_score is not None else None,
            "techniques": [link.technique.name for link in passage.technique_links],
            "cue": passage.practice_cue,
        }
        for passage in piece.hardest_passages[:4]
    ]
    interpretation = submission.interpretation if isinstance(submission.interpretation, dict) else None
    return {
        "piece": piece.title,
        "composer": piece.composer.name if piece.composer else None,
        "status": entry.status.value,
        "tempo": {"current": entry.current_tempo_bpm, "target": entry.target_tempo_bpm},
        "take": {
            "duration_sec": submission.duration_sec,
            "full_run_through": submission.is_full_run_through,
            "verification": submission.is_verification,
        },
        "tempo_match": interpretation if interpretation and interpretation.get("available") else None,
        "techniques": techniques,
        "hardest_passages": passages,
        "recent_notes": [note.body[:600] for note in notes],
    }


def weakest_passage(context: dict) -> Optional[dict]:
    order = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4, None: 2}
    tiers = {technique["name"]: technique["your_tier"] for technique in context["techniques"]}
    passages = context["hardest_passages"]
    if not passages:
        return None
    return min(
        passages,
        key=lambda passage: (
            min((order[tiers.get(name)] for name in passage["techniques"]), default=2),
            -(passage["difficulty"] or 0),
        ),
    )


def join_names(names: list[str]) -> str:
    lowered = [name.lower() for name in names]
    return lowered[0] if len(lowered) == 1 else ", ".join(lowered[:-1]) + " and " + lowered[-1]


def heuristic_feedback(context: dict) -> dict:
    focus = []
    target = weakest_passage(context)
    tiers = {technique["name"]: technique["your_tier"] for technique in context["techniques"]}
    for passage in [target] + [p for p in context["hardest_passages"] if p is not target][:1]:
        if passage is None:
            continue
        weak = [name for name in passage["techniques"] if tiers.get(name) in ("C", "D")]
        why = (
            f"It leans on {join_names(weak)}, which you ranked as {'a weaker area' if len(weak) == 1 else 'weaker areas'}."
            if weak
            else "It's one of the hardest marked passages in the piece."
        )
        focus.append(
            {
                "passage": f"{passage['label'] or 'Marked passage'} ({passage['bars']})",
                "why": why,
                "drill": passage["cue"] or "Loop it slowly, hands separately, then together at a tempo you can keep clean.",
            }
        )
    take = "full run-through" if context["take"]["full_run_through"] else "recording"
    summary = f"Thanks for logging this {take} of {context['piece']}."
    if context["tempo_match"]:
        summary += f" Your tempo shape matched the reference at {context['tempo_match'].get('match_score')}/100."
    return {
        "summary": summary,
        "focus": focus,
        "next_session": "Start with the first focus passage while you're fresh, then play the piece through once without stopping.",
    }


def prompt_for(context: dict) -> str:
    import json

    return (
        "Here is everything known about this upload, as JSON:\n"
        + json.dumps(context, ensure_ascii=False, indent=1)
        + "\n\nWrite coach notes: a 1-2 sentence summary, 1 to 3 focus items (each naming a passage from "
        "hardest_passages, why it matters for this student given their tiers and notes, and one concrete drill), "
        "and one sentence on how to structure the next practice session."
    )


def clean(output: dict) -> dict:
    focus = [
        {key: str(item.get(key, "")).strip() for key in ("passage", "why", "drill")}
        for item in (output.get("focus") or [])[:3]
        if isinstance(item, dict)
    ]
    return {
        "summary": str(output.get("summary") or "").strip(),
        "focus": [item for item in focus if item["passage"] and item["drill"]],
        "next_session": str(output.get("next_session") or "").strip(),
    }


async def generate_coach_feedback(submission_id: uuid.UUID | str) -> Optional[str]:
    submission_id = uuid.UUID(str(submission_id))
    async with session_scope() as session:
        submission = await session.get(AudioSubmission, submission_id)
        if submission is None or submission.processing_status != ProcessingStatus.DONE:
            return None
        generation = await ai.claim(session, PURPOSE, subject_key(submission_id))
        if generation is None:
            return "already generated"
        context = await gather_context(session, submission)
        if not ai.ai_enabled():
            ai.finish(generation, output=heuristic_feedback(context), model=HEURISTIC_MODEL)
            return HEURISTIC_MODEL
        try:
            completion = await ai.complete_json(prompt_for(context), SCHEMA, system=SYSTEM, max_tokens=2000)
        except Exception as error:
            logger.exception("coach feedback failed for submission %s", submission_id)
            ai.fail(generation, error)
            return "failed"
        completion.data = clean(completion.data)
        ai.finish(generation, completion)
        return completion.model


async def feedback_for(session: AsyncSession, submissions: Iterable[Submission]) -> dict[uuid.UUID, dict]:
    keys = {subject_key(submission.id): submission.id for submission in submissions if isinstance(submission, AudioSubmission)}
    if not keys:
        return {}
    rows = (
        await session.execute(
            select(AIGeneration).where(AIGeneration.purpose == PURPOSE, AIGeneration.subject_key.in_(keys))
        )
    ).scalars().all()
    feedback = {}
    for row in rows:
        if row.status == GenerationStatus.DONE and row.output:
            feedback[keys[row.subject_key]] = {**row.output, "model": row.model, "status": "done"}
        else:
            feedback[keys[row.subject_key]] = {"status": row.status.value}
    return feedback

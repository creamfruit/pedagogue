from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import AIGeneration, GenerationStatus

FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client = None


class GenerationRefused(RuntimeError):
    pass


@dataclass
class Completion:
    data: dict[str, Any]
    model: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]


def ai_enabled() -> bool:
    return bool(settings.anthropic_api_key)


def client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def complete_json(prompt: str, schema: dict[str, Any], *, system: Optional[str] = None, max_tokens: int = 4000) -> Completion:
    request: dict[str, Any] = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
        "output_config": {
            "effort": settings.anthropic_effort,
            "format": {"type": "json_schema", "schema": schema},
        },
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        request["system"] = system
    response = await client().beta.messages.create(**request)
    if response.stop_reason == "refusal":
        raise GenerationRefused(getattr(response.stop_details, "category", None) or "refused")
    text = next((block.text for block in response.content if getattr(block, "type", None) == "text"), None)
    if text is None:
        raise ValueError(f"no text block in response (stop_reason={response.stop_reason})")
    usage = response.usage
    return Completion(
        data=json.loads(text),
        model=response.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


async def claim(session: AsyncSession, purpose: str, subject_key: str) -> Optional[AIGeneration]:
    stmt = (
        insert(AIGeneration)
        .values(purpose=purpose, subject_key=subject_key, status=GenerationStatus.RUNNING)
        .on_conflict_do_nothing(constraint="uq_ai_generations_subject")
        .returning(AIGeneration.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    if inserted is None:
        return None
    return await session.get(AIGeneration, inserted)


async def existing(session: AsyncSession, purpose: str, subject_key: str) -> Optional[AIGeneration]:
    stmt = select(AIGeneration).where(AIGeneration.purpose == purpose, AIGeneration.subject_key == subject_key)
    return (await session.execute(stmt)).scalar_one_or_none()


def finish(generation: AIGeneration, completion: Optional[Completion] = None, *, output: Optional[dict] = None, model: Optional[str] = None) -> None:
    generation.status = GenerationStatus.DONE
    generation.output = completion.data if completion else output
    generation.model = completion.model if completion else model
    generation.input_tokens = completion.input_tokens if completion else None
    generation.output_tokens = completion.output_tokens if completion else None
    generation.completed_at = datetime.now(timezone.utc)


def fail(generation: AIGeneration, error: BaseException) -> None:
    generation.status = GenerationStatus.FAILED
    generation.error = f"{type(error).__name__}: {error}"[:2000]
    generation.completed_at = datetime.now(timezone.utc)

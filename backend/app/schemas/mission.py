from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class MissionStepRead(BaseModel):
    index: int
    kind: str
    title: str
    minutes: int
    why: str
    entry_id: Optional[str] = None
    piece_id: Optional[int] = None
    piece_title: Optional[str] = None
    composer: Optional[str] = None
    passage_id: Optional[int] = None
    bars: Optional[str] = None
    start_measure: Optional[int] = None
    end_measure: Optional[int] = None
    technique_id: Optional[int] = None
    technique: Optional[str] = None
    mechanic: Optional[str] = None
    cue: Optional[str] = None
    tempo_bpm: int = 72
    star_entry_id: Optional[str] = None


class MissionProgressRead(BaseModel):
    index: int
    status: str
    seconds: int = 0
    minutes: int = 0


class MissionRead(BaseModel):
    id: uuid.UUID
    day: date
    kind: str
    total_minutes: int
    steps: list[MissionStepRead]
    progress: list[MissionProgressRead]
    completed_at: Optional[datetime] = None
    next_index: Optional[int] = None


class MissionStepIn(BaseModel):
    status: Literal["done", "skipped"] = "done"
    seconds: int = Field(default=0, ge=0, le=7200)


class LitStar(BaseModel):
    entry_id: Optional[str] = None
    piece_title: Optional[str] = None


class MissionStepResult(BaseModel):
    mission: MissionRead
    lit: Optional[LitStar] = None
    finished: bool
    xp: int = 0
    gold: int = 0
    streak: dict[str, Any]

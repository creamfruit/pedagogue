from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

MAX_NOTES = 3000


class PlayedNoteIn(BaseModel):
    t: float = Field(ge=-5000, le=3_600_000)
    midi: int = Field(ge=0, le=127)


class AttemptIn(BaseModel):
    mode: Literal["scored", "wait", "free"]
    start_bar: Optional[int] = Field(default=None, ge=0, le=100000)
    end_bar: Optional[int] = Field(default=None, ge=0, le=100000)
    passage_id: Optional[int] = Field(default=None, ge=1)
    tempo_bpm: Optional[int] = Field(default=None, ge=20, le=400)
    beats_per_bar: int = Field(default=4, ge=1, le=16)
    count_in_beats: int = Field(default=4, ge=0, le=16)
    latency_ms: float = Field(default=0.0, ge=-500, le=500)
    duration_sec: float = Field(default=0.0, ge=0, le=7200)
    notes: list[PlayedNoteIn] = Field(default_factory=list, max_length=MAX_NOTES)

    @model_validator(mode="after")
    def check_mode(self) -> "AttemptIn":
        if self.mode in {"scored", "free"} and self.tempo_bpm is None:
            raise ValueError("choose a tempo")
        if self.mode in {"scored", "wait"}:
            if self.start_bar is None or self.end_bar is None:
                raise ValueError("choose the bars to play")
            if self.end_bar < self.start_bar:
                raise ValueError("the last bar can't come before the first")
        return self


class BarOut(BaseModel):
    bar: int
    expected: int = 0
    correct: int = 0
    wrong: int = 0
    missing: int = 0
    accuracy: Optional[float] = None
    tempo_bpm: Optional[float] = None
    timing_error_ms: Optional[float] = None
    timing_score: Optional[float] = None
    late: int = 0
    early: int = 0


class LadderOut(BaseModel):
    recommended_tempo: int
    current_tempo: Optional[int] = None
    clean_streak: int = 0
    runs_needed: int
    target_tempo: int
    raised: bool = False
    reached_target: bool = False


class AttemptOut(BaseModel):
    id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
    mode: str
    passage_id: Optional[int] = None
    start_bar: Optional[int] = None
    end_bar: Optional[int] = None
    tempo_bpm: Optional[int] = None
    achieved_tempo_bpm: Optional[float] = None
    expected: int = 0
    correct: int = 0
    wrong: int = 0
    missing: int = 0
    played: int = 0
    accuracy: Optional[float] = None
    timing: Optional[float] = None
    evenness: Optional[float] = None
    overall: float = 0.0
    clean: bool = False
    late: int = 0
    early: int = 0
    duration_sec: float = 0.0
    bars: list[BarOut] = Field(default_factory=list)
    ladder: Optional[LadderOut] = None
    note_checking: bool = True
    message: Optional[str] = None


class PassagePick(BaseModel):
    id: int
    label: str
    start_bar: int
    end_bar: int


class ReferenceOut(BaseModel):
    available: bool
    source: Optional[str] = None
    first_bar: Optional[int] = None
    last_bar: Optional[int] = None
    quarter_bpm: Optional[float] = None
    beats_per_bar: int = 4
    note_count: int = 0
    target_tempo_bpm: int
    passages: list[PassagePick] = Field(default_factory=list)
    message: Optional[str] = None


class ReferenceNotesOut(BaseModel):
    start_bar: int
    end_bar: int
    quarter_bpm: float
    beats_per_bar: int
    bars: list[int]
    notes: list[list[float]]

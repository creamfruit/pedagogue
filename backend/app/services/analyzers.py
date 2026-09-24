from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectin_polymorphic, selectinload

from app.core.storage import Storage, storage as default_storage
from app.models.models import (
    Analysis,
    AudioSubmission,
    Passage,
    PassageAssessment,
    PassageSource,
    PassageTechnique,
    PdfSubmission,
    Piece,
    ProcessingStatus,
    Submission,
    SubmissionType,
    Technique,
    TextSubmission,
)
from app.services.interpretation import compare_curves, reference_curve

ANALYZER_VERSION = "0.1.0"

TECHNIQUE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Double thirds": ("double third", "thirds", "3rds"),
    "Double sixths": ("double sixth", "sixths", "6ths"),
    "Broken octaves": ("broken octave", "octave tremolo"),
    "Blocked octaves": ("octave", "octaves"),
    "Wide leaps": ("leap", "jump", "stride"),
    "Repeated chords": ("repeated chord", "chord repetition"),
    "Rapid scales": ("scale", "scalar", "run", "runs"),
    "Arpeggio figuration": ("arpeggio", "arpeggios", "broken chord"),
    "Repeated notes": ("repeated note",),
    "Trills": ("trill", "ornament", "mordent"),
    "Tenth stretches": ("tenth", "stretch", "span"),
    "Three against two": ("3 against 2", "three against two", "3:2"),
    "Four against three": ("4 against 3", "four against three", "4:3"),
    "Melody over accompaniment": ("melody", "cantabile", "singing tone"),
    "Inner voice projection": ("inner voice", "voicing", "counterpoint"),
    "Half pedalling": ("pedal", "pedalling", "pedaling"),
    "Sustained endurance": ("endurance", "stamina", "tension", "fatigue"),
}

MEASURE_PATTERN = re.compile(
    r"(?:bars?|measures?|mm?\.)\s*(\d{1,4})(?:\s*(?:-|–|to|through)\s*(\d{1,4}))?",
    re.IGNORECASE,
)


@dataclass
class PassageFinding:
    start_measure: int
    end_measure: int
    label: Optional[str] = None
    difficulty: Optional[float] = None
    description: Optional[str] = None
    techniques: dict[str, float] = field(default_factory=dict)
    accuracy: Optional[float] = None
    tempo_stability: Optional[float] = None
    voicing_balance: Optional[float] = None
    restarts: int = 0
    memory_slip: bool = False


@dataclass
class AnalysisResult:
    summary: str
    raw: dict[str, Any]
    findings: list[PassageFinding] = field(default_factory=list)


class Analyzer(ABC):
    name: str = "analyzer"
    handles: SubmissionType

    def __init__(self, session: AsyncSession, storage: Optional[Storage] = None) -> None:
        self.session = session
        self.storage = storage or default_storage

    @abstractmethod
    async def analyze(self, submission: Submission) -> AnalysisResult: ...

    async def run(self, submission: Submission) -> Analysis:
        submission.mark(ProcessingStatus.PROCESSING)
        await self.session.flush()
        try:
            result = await self.analyze(submission)
        except Exception as exc:
            submission.mark(ProcessingStatus.FAILED)
            analysis = Analysis(
                submission_id=submission.id,
                analyzer_name=self.name,
                analyzer_version=ANALYZER_VERSION,
                summary=f"analysis failed: {exc}",
                raw_result={"error": str(exc), "error_type": type(exc).__name__},
            )
            self.session.add(analysis)
            await self.session.flush()
            return analysis

        analysis = Analysis(
            submission_id=submission.id,
            analyzer_name=self.name,
            analyzer_version=ANALYZER_VERSION,
            summary=result.summary,
            raw_result=result.raw,
        )
        self.session.add(analysis)
        await self.session.flush()

        piece_id = submission.repertoire_entry.piece_id
        for finding in result.findings:
            passage = await self.upsert_passage(piece_id, finding)
            self.session.add(
                PassageAssessment(
                    analysis_id=analysis.id,
                    passage_id=passage.id,
                    accuracy_score=self.to_decimal(finding.accuracy, 3),
                    tempo_stability=self.to_decimal(finding.tempo_stability, 3),
                    voicing_balance=self.to_decimal(finding.voicing_balance, 3),
                    restart_count=finding.restarts,
                    memory_slip=finding.memory_slip,
                )
            )
        submission.mark(ProcessingStatus.DONE)
        await self.session.flush()
        return analysis

    @staticmethod
    def to_decimal(value: Optional[float], places: int) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(str(round(value, places)))

    async def upsert_passage(self, piece_id: int, finding: PassageFinding) -> Passage:
        stmt = select(Passage).where(
            Passage.piece_id == piece_id,
            Passage.start_measure == finding.start_measure,
            Passage.end_measure == finding.end_measure,
        )
        result = await self.session.execute(stmt)
        passage = result.scalar_one_or_none()
        if passage is None:
            passage = Passage(
                piece_id=piece_id,
                start_measure=finding.start_measure,
                end_measure=finding.end_measure,
                label=finding.label,
                difficulty_score=self.to_decimal(finding.difficulty, 1),
                source=PassageSource.ANALYZER,
                description=finding.description,
            )
            self.session.add(passage)
            await self.session.flush()
        elif finding.description and not passage.description:
            passage.description = finding.description
        await self.link_techniques(passage, finding.techniques)
        return passage

    async def link_techniques(self, passage: Passage, weights: dict[str, float]) -> None:
        if not weights:
            return
        stmt = select(Technique).where(Technique.name.in_(list(weights)))
        result = await self.session.execute(stmt)
        by_name = {technique.name: technique for technique in result.scalars().all()}
        linked = await self.session.execute(
            select(PassageTechnique.technique_id).where(PassageTechnique.passage_id == passage.id)
        )
        existing = set(linked.scalars().all())
        for name, weight in weights.items():
            technique = by_name.get(name)
            if technique is None or technique.id in existing:
                continue
            self.session.add(
                PassageTechnique(
                    passage_id=passage.id,
                    technique_id=technique.id,
                    weight=Decimal(str(round(min(max(weight, 0.0), 1.0), 2))),
                )
            )

    @staticmethod
    def detect_techniques(text: str) -> dict[str, float]:
        lowered = text.lower()
        found: dict[str, float] = {}
        for name, keywords in TECHNIQUE_KEYWORDS.items():
            hits = sum(lowered.count(keyword) for keyword in keywords)
            if hits:
                found[name] = min(0.4 + 0.2 * hits, 1.0)
        return found

    @staticmethod
    def detect_measures(text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for match in MEASURE_PATTERN.finditer(text):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            if end < start:
                start, end = end, start
            spans.append((start, end))
        return spans


class TextAnalyzer(Analyzer):
    name = "text-notes"
    handles = SubmissionType.TEXT

    async def analyze(self, submission: Submission) -> AnalysisResult:
        assert isinstance(submission, TextSubmission)
        body = submission.body
        spans = self.detect_measures(body)
        techniques = self.detect_techniques(body)
        findings = [
            PassageFinding(
                start_measure=start,
                end_measure=end,
                label="flagged in notes",
                description=body[:280],
                techniques=techniques,
                difficulty=None,
            )
            for start, end in spans
        ]
        summary = (
            f"parsed {submission.word_count} words, "
            f"found {len(spans)} measure references and {len(techniques)} techniques"
        )
        return AnalysisResult(
            summary=summary,
            raw={
                "word_count": submission.word_count,
                "measure_spans": spans,
                "techniques": techniques,
            },
            findings=findings,
        )


class ScoreAnalyzer(Analyzer):
    name = "score-omr"
    handles = SubmissionType.PDF

    async def analyze(self, submission: Submission) -> AnalysisResult:
        assert isinstance(submission, PdfSubmission)
        if not self.storage.exists(submission.storage_key):
            raise FileNotFoundError(f"stored score missing: {submission.storage_key}")
        page_count = submission.page_count or self.count_pages(submission.storage_key)
        submission.page_count = page_count
        submission.omr_confidence = Decimal("0.00")
        return AnalysisResult(
            summary=(
                f"score ingested across {page_count} page(s); "
                "optical music recognition not yet wired, no passages extracted"
            ),
            raw={
                "stage": "ingested",
                "page_count": page_count,
                "storage_key": submission.storage_key,
                "next_step": "run Audiveris to produce MusicXML, then extract bar features with music21",
            },
            findings=[],
        )

    def count_pages(self, key: str) -> int:
        try:
            try:
                import pymupdf
            except ImportError:
                import fitz as pymupdf

            with self.storage.open(key) as handle:
                document = pymupdf.open(stream=handle.read(), filetype="pdf")
                return document.page_count
        except Exception:
            return 0


class AudioAnalyzer(Analyzer):
    name = "audio-transcription"
    handles = SubmissionType.AUDIO

    async def analyze(self, submission: Submission) -> AnalysisResult:
        assert isinstance(submission, AudioSubmission)
        if not self.storage.exists(submission.storage_key):
            raise FileNotFoundError(f"stored recording missing: {submission.storage_key}")

        interpretation = None
        if submission.tempo_curve:
            piece_id = submission.repertoire_entry.piece_id
            piece = await self.session.get(Piece, piece_id)
            reference = reference_curve(
                piece_id, submission.duration_sec or (piece.duration_sec if piece else None),
                piece.tempo_marking if piece else None,
            )
            raw_curve = submission.tempo_curve
            points = raw_curve.get("points") if isinstance(raw_curve, dict) else raw_curve
            interpretation = compare_curves(points if isinstance(points, list) else [], reference)
            submission.interpretation = interpretation

        summary = f"recording ingested ({submission.duration_label}); "
        summary += (
            f"interpretation match {interpretation['match_score']}/100"
            if interpretation and interpretation.get("available")
            else "transcription and score alignment not yet wired, no assessments produced"
        )
        return AnalysisResult(
            summary=summary,
            raw={
                "stage": "ingested",
                "duration_sec": submission.duration_sec,
                "is_full_run_through": submission.is_full_run_through,
                "storage_key": submission.storage_key,
                "interpretation": interpretation,
                "next_step": "transcribe to MIDI, align to score with DTW, score each bar",
            },
            findings=[],
        )


ANALYZERS: dict[SubmissionType, type[Analyzer]] = {
    SubmissionType.TEXT: TextAnalyzer,
    SubmissionType.PDF: ScoreAnalyzer,
    SubmissionType.AUDIO: AudioAnalyzer,
}


def analyzer_for(submission: Submission, session: AsyncSession, storage: Optional[Storage] = None) -> Analyzer:
    analyzer_cls = ANALYZERS.get(submission.submission_type)
    if analyzer_cls is None:
        raise ValueError(f"no analyzer for {submission.submission_type}")
    return analyzer_cls(session, storage)


async def load_submission(session: AsyncSession, submission_id) -> Optional[Submission]:
    stmt = (
        select(Submission)
        .options(
            selectin_polymorphic(Submission, [TextSubmission, PdfSubmission, AudioSubmission]),
            selectinload(Submission.repertoire_entry),
        )
        .where(Submission.id == submission_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

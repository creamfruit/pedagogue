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
    PieceTechnique,
    ProcessingStatus,
    RepertoireEntry,
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
    practice_cue: Optional[str] = None


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
                practice_cue=finding.practice_cue,
            )
            self.session.add(passage)
            await self.session.flush()
        else:
            if finding.description and (not passage.description or passage.source == PassageSource.ANALYZER):
                passage.description = finding.description
            if finding.practice_cue and not passage.practice_cue:
                passage.practice_cue = finding.practice_cue
            if passage.source == PassageSource.ANALYZER and finding.label:
                passage.label = finding.label
            if passage.difficulty_score is None and finding.difficulty is not None:
                passage.difficulty_score = self.to_decimal(finding.difficulty, 1)
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


PDF_PASSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "passages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_bar": {"type": "integer"},
                    "end_bar": {"type": "integer"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "techniques": {"type": "array", "items": {"type": "string", "enum": list(TECHNIQUE_KEYWORDS)}},
                },
                "required": ["start_bar", "end_bar", "label", "description", "techniques"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["readable", "passages"],
    "additionalProperties": False,
}

PDF_PROMPT = (
    "This PDF is piano sheet music for {title}. Find the three to five hardest passages. "
    "Use the bar numbers printed in the score; if bars are not numbered, count from the first full bar. "
    "Only report a passage when you can actually read it on the page. For each one give the bar range, a short label, "
    "one sentence on what makes it hard, and the techniques involved. Set readable to false if this is not piano music "
    "or you cannot read it."
)


class ScoreAnalyzer(Analyzer):
    name = "score"
    handles = SubmissionType.PDF

    async def analyze(self, submission: Submission) -> AnalysisResult:
        assert isinstance(submission, PdfSubmission)
        if not self.storage.exists(submission.storage_key):
            raise FileNotFoundError(f"stored score missing: {submission.storage_key}")
        suffix = "." + submission.storage_key.rsplit(".", 1)[-1].lower() if "." in submission.storage_key else ".pdf"
        with self.storage.open(submission.storage_key) as handle:
            data = handle.read()
        if suffix == ".pdf":
            return await self.analyze_pdf(submission, data)
        return await self.analyze_digital(submission, data, suffix)

    async def analyze_digital(self, submission: PdfSubmission, data: bytes, suffix: str) -> AnalysisResult:
        import asyncio

        from app.services.score_analysis import analyse_file

        report = await asyncio.to_thread(analyse_file, data, f"score{suffix}")
        submission.omr_confidence = Decimal("1.00")
        piece = submission.repertoire_entry.piece
        await self.update_difficulty(piece, report)
        base = float(piece.difficulty_score) / 10 if piece.difficulty_score is not None else report.estimated_difficulty / 10
        findings = [
            PassageFinding(
                start_measure=passage.start,
                end_measure=passage.end,
                label=passage.label,
                description=passage.description,
                techniques=passage.techniques,
                difficulty=round(min(10.0, base * (0.82 + 0.22 * passage.difficulty)), 1),
                practice_cue=passage.cue,
            )
            for passage in report.passages
        ]
        await self.update_piece(piece, report)
        return AnalysisResult(
            summary=(
                f"read {report.measures} bars and {report.notes} notes; "
                f"marked {len(findings)} hard passage(s) on the piece page"
            ),
            raw={
                "stage": "analysed",
                "bars": report.measures,
                "notes": report.notes,
                "duration_sec": report.duration_sec,
                "techniques": report.techniques,
                "estimated_difficulty": report.estimated_difficulty,
            },
            findings=findings,
        )

    async def update_difficulty(self, piece: Piece, report) -> None:
        from app.services.score_library import calibrated_difficulty

        model = piece.metadata_generation_model or ""
        if not (piece.is_user_created or model.startswith("heuristic")):
            return
        value = calibrated_difficulty(report.features)
        if value is not None:
            piece.difficulty_score = value

    async def update_piece(self, piece: Piece, report) -> None:
        from app.services.piece_knowledge import is_offline_generated, replace_techniques

        if piece.duration_sec is None and report.duration_sec:
            piece.duration_sec = int(report.duration_sec)
        linked = await self.session.execute(select(PieceTechnique.technique_id).where(PieceTechnique.piece_id == piece.id))
        if is_offline_generated(piece) or not linked.scalars().first():
            techniques = {t.name: t for t in (await self.session.execute(select(Technique))).scalars().all()}
            await replace_techniques(self.session, piece, list(report.techniques), techniques)

    async def analyze_pdf(self, submission: PdfSubmission, data: bytes) -> AnalysisResult:
        import asyncio

        from app.services import ai
        from app.services.pdf_layout import analyse_pdf

        piece = submission.repertoire_entry.piece
        try:
            layout = await asyncio.to_thread(analyse_pdf, data)
        except Exception:
            layout = None
        page_count = submission.page_count or (layout.pages if layout else self.count_pages(submission.storage_key))
        submission.page_count = page_count

        if ai.ai_enabled():
            try:
                findings, model = await self.read_with_ai(piece, data)
            except Exception:
                findings, model = [], None
            if findings:
                crops = await self.save_crops(submission, layout, [(f.start_measure, f.end_measure) for f in findings])
                submission.omr_confidence = Decimal("0.70")
                return AnalysisResult(
                    summary=f"read {page_count} page(s) and marked {len(findings)} hard passage(s)",
                    raw={"stage": "read", "page_count": page_count, "model": model, "crops": crops, "bars": layout.bar_count if layout else None},
                    findings=findings,
                )

        if layout is None or not layout.readable:
            submission.omr_confidence = Decimal("0.00")
            return AnalysisResult(
                summary=(
                    f"score saved ({page_count} page(s)), but the staves could not be read from it. "
                    "A clean digital PDF works best; MusicXML or MIDI gives exact passages"
                ),
                raw={"stage": "stored", "page_count": page_count},
                findings=[],
            )

        existing = (
            await self.session.execute(
                select(Passage).where(Passage.piece_id == piece.id, Passage.source == PassageSource.CATALOG)
            )
        ).scalars().all()
        spans: list[tuple[int, int]] = [(p.start_measure, p.end_measure) for p in existing if p.start_measure <= layout.bar_count]
        findings: list[PassageFinding] = []
        if not existing:
            profile = await self.piece_profile(piece)
            base = float(piece.difficulty_score) / 10 if piece.difficulty_score is not None else 6.0
            for dense in layout.passages:
                top = [name for name, _ in profile[:2]]
                findings.append(
                    PassageFinding(
                        start_measure=dense.start,
                        end_measure=dense.end,
                        label=f"Dense writing, page {dense.page}",
                        description=(
                            f"Around bars {dense.start}\u2013{dense.end} on page {dense.page}, the busiest writing in your score: "
                            f"about {dense.relative:g} times the ink of a typical bar. Bar numbers are counted from the page, "
                            "so check them against your copy."
                        ),
                        techniques={name: weight for name, weight in profile[:2]},
                        difficulty=round(min(10.0, base * (0.8 + 0.12 * dense.relative)), 1),
                        practice_cue=(
                            f"Slow this section right down and work on {top[0].lower()} first." if top else "Slow this section right down and learn it hands separately first."
                        ),
                    )
                )
            spans = [(f.start_measure, f.end_measure) for f in findings]
        crops = await self.save_crops(submission, layout, spans)
        submission.omr_confidence = Decimal("0.45")
        marked = f"marked {len(findings)} dense passage(s)" if findings else f"matched {len(crops)} known hard passage(s) to your pages"
        return AnalysisResult(
            summary=f"read {page_count} page(s), counted about {layout.bar_count} bars and {marked}",
            raw={"stage": "layout", "page_count": page_count, "bars": layout.bar_count, "systems": len(layout.systems), "crops": crops},
            findings=findings,
        )

    async def piece_profile(self, piece: Piece) -> list[tuple[str, float]]:
        rows = (
            await self.session.execute(
                select(Technique.name, PieceTechnique.weight)
                .join(PieceTechnique, PieceTechnique.technique_id == Technique.id)
                .where(PieceTechnique.piece_id == piece.id)
                .order_by(PieceTechnique.weight.desc())
            )
        ).all()
        if rows:
            return [(name, float(weight)) for name, weight in rows]
        from app.models.models import Composer
        from app.services.repertoire_reference import heuristic_techniques

        name = None
        if piece.composer_id:
            name = (await self.session.execute(select(Composer.name).where(Composer.id == piece.composer_id))).scalar_one_or_none()
        return heuristic_techniques(piece.title, name)

    async def save_crops(self, submission: PdfSubmission, layout, spans: list[tuple[int, int]]) -> list[dict]:
        import asyncio
        import io

        from app.services.pdf_layout import DensePassage, crop_png

        if layout is None or not layout.readable:
            return []
        crops = []
        by_number = {bar.number: bar for bar in layout.bars}
        for index, (start, end) in enumerate(spans[:12]):
            bars = [by_number[n] for n in range(start, end + 1) if n in by_number]
            if not bars:
                continue
            boxes: dict[int, list[int]] = {}
            for bar in bars:
                if bar.system not in boxes and len(boxes) >= 3:
                    break
                box = boxes.setdefault(bar.system, [bar.page, bar.x0, bar.y0, bar.x1, bar.y1])
                box[1] = min(box[1], bar.x0)
                box[3] = max(box[3], bar.x1)
            region = DensePassage(start, end, bars[0].page + 1, 1.0, [tuple(box) for box in boxes.values()])
            png = await asyncio.to_thread(crop_png, layout, region)
            key = submission.storage_key.rsplit(".", 1)[0] + f".crop{index}.png"
            self.storage.save(io.BytesIO(png), key)
            crops.append({"start": start, "end": end, "page": region.page, "key": key})
        return crops

    async def read_with_ai(self, piece: Piece, data: bytes) -> tuple[list[PassageFinding], Optional[str]]:
        import base64

        from app.services import ai

        completion = await ai.complete_json(
            PDF_PROMPT.format(title=piece.title),
            PDF_PASSAGE_SCHEMA,
            max_tokens=3000,
            pdf_base64=base64.b64encode(data).decode(),
        )
        output = completion.data
        passages = output.get("passages") or [] if output.get("readable") else []
        findings = []
        for item in passages[:6]:
            start, end = int(item.get("start_bar") or 0), int(item.get("end_bar") or 0)
            if start < 1 or end < start or end - start > 64:
                continue
            findings.append(
                PassageFinding(
                    start_measure=start,
                    end_measure=end,
                    label=str(item.get("label") or "Hard passage")[:80],
                    description=str(item.get("description") or "")[:500] or None,
                    techniques={name: 0.8 for name in item.get("techniques") or [] if name in TECHNIQUE_KEYWORDS},
                    difficulty=None,
                )
            )
        return findings, completion.model

    def count_pages(self, key: str) -> int:
        try:
            import pypdfium2 as pdfium

            with self.storage.open(key) as handle:
                document = pdfium.PdfDocument(handle.read())
                count = len(document)
                document.close()
                return count
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
            selectinload(Submission.repertoire_entry).selectinload(RepertoireEntry.piece),
        )
        .where(Submission.id == submission_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

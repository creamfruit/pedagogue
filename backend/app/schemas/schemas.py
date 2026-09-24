from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

from app.models.models import (
    FlaggedBy,
    GenreFamily,
    LinkType,
    PassageSource,
    CosmeticKind,
    DrillType,
    LedgerReason,
    LoadSeverity,
    PlanStepStatus,
    PracticeMode,
    ProcessingStatus,
    RecommendationStatus,
    ProfileVisibility,
    RepertoireStatus,
    SelfLevel,
    SelfRating,
    SubmissionType,
    TechniqueCategory,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if value.isalpha() or value.isdigit():
            raise ValueError("password must mix letters and numbers")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    display_name: Optional[str]
    avatar_url: Optional[str]
    years_playing: Optional[int]
    self_level: Optional[SelfLevel]
    hand_span_cm: Optional[Decimal]
    profile_visibility: ProfileVisibility
    tier_quiz_completed_at: Optional[datetime] = None
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=80)
    avatar_url: Optional[str] = None
    years_playing: Optional[int] = Field(default=None, ge=0, le=100)
    self_level: Optional[SelfLevel] = None
    hand_span_cm: Optional[Decimal] = Field(default=None, ge=10, le=35)
    profile_visibility: Optional[ProfileVisibility] = None


class EraRead(ORMModel):
    id: int
    name: str
    start_year: Optional[int]
    end_year: Optional[int]


class GenreRead(ORMModel):
    id: int
    name: str
    family: GenreFamily


class ComposerRead(ORMModel):
    id: int
    name: str
    birth_year: Optional[int]
    death_year: Optional[int]
    nationality: Optional[str]
    era_id: Optional[int]


class TechniqueRead(ORMModel):
    id: int
    name: str
    category: TechniqueCategory
    parent_technique_id: Optional[int]
    load_factor: Decimal
    description: Optional[str]


class PieceRead(ORMModel):
    id: int
    title: str
    composer_id: Optional[int]
    genre_id: Optional[int]
    catalog_number: Optional[str]
    key_signature: Optional[str]
    difficulty_score: Optional[Decimal]
    mechanical_load: Optional[Decimal] = None
    syllabus_grade: Optional[str] = None
    duration_sec: Optional[int]
    parent_piece_id: Optional[int]
    movement_number: Optional[int]
    is_user_created: bool
    is_custom: bool = False
    external_source: Optional[str] = None
    requires_verification: bool = False


class PieceDetail(PieceRead):
    composer: Optional[ComposerRead] = None
    genre: Optional[GenreRead] = None


class PieceTechniqueWeightIn(BaseModel):
    technique_id: int
    weight: float = Field(ge=0, le=1)


class PieceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    composer_id: Optional[int] = None
    composer_name: Optional[str] = Field(default=None, max_length=120)
    genre_id: Optional[int] = None
    catalog_number: Optional[str] = Field(default=None, max_length=40)
    key_signature: Optional[str] = Field(default=None, max_length=20)
    difficulty_score: Optional[Decimal] = Field(default=None, ge=0, le=100)
    mechanical_load: Optional[Decimal] = Field(default=None, ge=0, le=100)
    duration_sec: Optional[int] = Field(default=None, ge=0)
    techniques: list[PieceTechniqueWeightIn] = Field(default_factory=list, max_length=20)
    custom_style: Optional[dict[str, Any]] = None


class ExternalCandidate(BaseModel):
    external_ref: str
    title: str
    subtitle: Optional[str] = None
    composer_name: str
    composer_external_ref: Optional[str] = None
    epoch: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None


class ExternalImportRequest(BaseModel):
    external_ref: str
    title: str = Field(min_length=1, max_length=200)
    composer_name: Optional[str] = Field(default=None, max_length=120)
    genre_id: Optional[int] = None
    duration_sec: Optional[int] = Field(default=None, ge=0)


class GenrePreferenceUpdate(BaseModel):
    genre_ids: list[int] = Field(default_factory=list, max_length=20)


class ComposerPreferenceItem(BaseModel):
    composer_id: int
    rank: Optional[int] = Field(default=None, ge=1, le=20)


class ComposerPreferenceUpdate(BaseModel):
    composers: list[ComposerPreferenceItem] = Field(default_factory=list, max_length=20)


class TechniqueProfileItem(BaseModel):
    technique_id: int
    self_rating: SelfRating = SelfRating.NEUTRAL
    proficiency_score: Optional[Decimal] = Field(default=None, ge=0, le=10)


class TechniqueProfileUpdate(BaseModel):
    techniques: list[TechniqueProfileItem] = Field(default_factory=list, max_length=40)


class TechniqueProfileRead(ORMModel):
    technique_id: int
    self_rating: SelfRating
    proficiency_score: Optional[Decimal]
    updated_at: datetime
    technique: TechniqueRead


class RepertoireEntryCreate(BaseModel):
    piece_id: Optional[int] = None
    piece: Optional[PieceCreate] = None
    status: RepertoireStatus = RepertoireStatus.LEARNING
    is_top_ten: bool = False
    top_ten_rank: Optional[int] = Field(default=None, ge=1, le=10)
    current_tempo_bpm: Optional[int] = Field(default=None, ge=20, le=300)
    target_tempo_bpm: Optional[int] = Field(default=None, ge=20, le=300)
    started_on: Optional[date] = None
    notes: Optional[str] = None

    @field_validator("piece")
    @classmethod
    def one_source(cls, value: Optional[PieceCreate], info) -> Optional[PieceCreate]:
        if value is None and info.data.get("piece_id") is None:
            raise ValueError("provide either piece_id or piece")
        return value


class RepertoireEntryUpdate(BaseModel):
    status: Optional[RepertoireStatus] = None
    is_top_ten: Optional[bool] = None
    top_ten_rank: Optional[int] = Field(default=None, ge=1, le=10)
    current_tempo_bpm: Optional[int] = Field(default=None, ge=20, le=300)
    target_tempo_bpm: Optional[int] = Field(default=None, ge=20, le=300)
    started_on: Optional[date] = None
    completed_on: Optional[date] = None
    notes: Optional[str] = None


class RepertoireEntryRead(ORMModel):
    id: uuid.UUID
    piece_id: int
    status: RepertoireStatus
    is_top_ten: bool
    top_ten_rank: Optional[int]
    current_tempo_bpm: Optional[int]
    target_tempo_bpm: Optional[int]
    started_on: Optional[date]
    completed_on: Optional[date]
    notes: Optional[str]
    is_verified: bool = False
    last_practiced_at: Optional[datetime] = None
    needs_verification: bool = False
    decay_level: float = 0.0
    is_frozen: bool = False
    piece: PieceDetail


class TopTenItem(BaseModel):
    rank: int = Field(ge=1, le=10)
    piece_id: Optional[int] = None
    piece: Optional[PieceCreate] = None


class TopTenSubmit(BaseModel):
    pieces: list[TopTenItem] = Field(min_length=1, max_length=10)


class OnboardingStatus(BaseModel):
    profile_complete: bool
    genres_chosen: int
    composers_chosen: int
    techniques_rated: int
    top_ten_logged: int
    tier_quiz_complete: bool
    complete: bool

    @computed_field
    @property
    def next_step(self) -> str:
        if not self.profile_complete:
            return "profile"
        if not self.tier_quiz_complete:
            return "tier_quiz"
        if self.top_ten_logged == 0:
            return "top_ten"
        if self.genres_chosen == 0 or self.composers_chosen == 0:
            return "tastes"
        return "done"


class TierAssignment(BaseModel):
    technique_id: int
    tier: str = Field(pattern="^[SABCDsabcd]$")


class TierListSubmit(BaseModel):
    tiers: list[TierAssignment] = Field(min_length=1, max_length=40)


class OnboardingSummary(BaseModel):
    user: UserRead
    status: OnboardingStatus
    genres: list[GenreRead]
    composers: list[ComposerRead]
    techniques: list[TechniqueProfileRead]
    top_ten: list[RepertoireEntryRead]


class PassageRead(ORMModel):
    id: int
    piece_id: int
    start_measure: int
    end_measure: int
    label: Optional[str]
    difficulty_score: Optional[Decimal]
    source: PassageSource
    description: Optional[str]


class PassageAssessmentRead(ORMModel):
    id: uuid.UUID
    passage_id: int
    accuracy_score: Optional[Decimal]
    tempo_stability: Optional[Decimal]
    voicing_balance: Optional[Decimal]
    restart_count: int
    memory_slip: bool
    flagged_by: FlaggedBy
    passage: PassageRead


class AnalysisRead(ORMModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    analyzer_name: str
    analyzer_version: str
    summary: Optional[str]
    created_at: datetime


class AnalysisDetail(AnalysisRead):
    raw_result: Optional[dict[str, Any]] = None
    passage_assessments: list[PassageAssessmentRead] = Field(default_factory=list)


class SubmissionRead(ORMModel):
    id: uuid.UUID
    repertoire_entry_id: uuid.UUID
    submission_type: SubmissionType
    processing_status: ProcessingStatus
    created_at: datetime


class TextSubmissionRead(SubmissionRead):
    body: str


class PdfSubmissionRead(SubmissionRead):
    storage_key: str
    page_count: Optional[int]
    musicxml_key: Optional[str]
    omr_confidence: Optional[Decimal]


class AudioSubmissionRead(SubmissionRead):
    storage_key: str
    duration_sec: Optional[int]
    is_full_run_through: bool
    is_verification: bool = False
    midi_key: Optional[str]
    tempo_curve: Optional[dict[str, Any]] = None


class SubmissionDetail(SubmissionRead):
    analyses: list[AnalysisRead] = Field(default_factory=list)
    body: Optional[str] = None
    storage_key: Optional[str] = None
    page_count: Optional[int] = None
    musicxml_key: Optional[str] = None
    omr_confidence: Optional[Decimal] = None
    duration_sec: Optional[int] = None
    is_full_run_through: Optional[bool] = None
    is_verification: Optional[bool] = None
    midi_key: Optional[str] = None
    tempo_curve: Optional[dict[str, Any]] = None
    interpretation: Optional[dict[str, Any]] = None


class TextSubmissionCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class SubmissionAccepted(BaseModel):
    submission: SubmissionRead
    queued: bool
    poll_url: str


class RepertoireStats(BaseModel):
    total: int
    by_status: dict[str, int]
    active: int
    submissions: int
    pending_submissions: int
    average_difficulty: Optional[float]


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class RepertoirePage(BaseModel):
    meta: PageMeta
    items: list[RepertoireEntryRead]


class ScoredPieceRead(BaseModel):
    piece: PieceDetail
    score: float
    overlap: float
    coverage: float
    gap: float
    shared_techniques: list[str]
    rationale: str


class PrerequisiteResponse(BaseModel):
    target: PieceDetail
    prerequisites: list[ScoredPieceRead]
    persisted: bool


class SteppingStoneResponse(BaseModel):
    target: PieceDetail
    comfort_ceiling: float
    path: list[ScoredPieceRead]
    total_steps: int


class RecommendationRead(ORMModel):
    id: uuid.UUID
    target_piece_id: int
    recommended_piece_id: int
    score: Optional[Decimal]
    reason: Optional[str]
    status: RecommendationStatus
    created_at: datetime
    recommended_piece: PieceDetail


class RecommendationDecision(BaseModel):
    status: RecommendationStatus


class ConstellationNode(BaseModel):
    id: int
    entry_id: str
    title: str
    composer: Optional[str]
    composer_id: Optional[int]
    genre: Optional[str]
    era: Optional[str]
    difficulty: float
    radius: float
    status: str
    is_top_ten: bool
    is_verified: bool = True
    is_custom: bool = False
    decay: float = 0.0


class ConstellationLink(BaseModel):
    source: int
    target: int
    link_type: str
    strength: float
    label: str


class ConstellationGraph(BaseModel):
    nodes: list[ConstellationNode]
    links: list[ConstellationLink]
    link_types: list[str]
    counts: dict[str, int]


class PracticeSessionStart(BaseModel):
    mode: PracticeMode = PracticeMode.FREE
    notes: Optional[str] = Field(default=None, max_length=2000)


class PracticeSessionClose(BaseModel):
    perceived_tension: Optional[int] = Field(default=None, ge=1, le=5)


class SessionItemCreate(BaseModel):
    minutes: int = Field(ge=1, le=600)
    repertoire_entry_id: Optional[uuid.UUID] = None
    passage_id: Optional[int] = None
    drill_id: Optional[uuid.UUID] = None


class SessionItemRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    repertoire_entry_id: Optional[uuid.UUID]
    passage_id: Optional[int]
    drill_id: Optional[uuid.UUID]
    minutes: Optional[int]
    load_units: Optional[Decimal]
    target_label: str


class PracticeSessionRead(ORMModel):
    id: uuid.UUID
    mode: PracticeMode
    started_at: datetime
    ended_at: Optional[datetime]
    perceived_tension: Optional[int]
    notes: Optional[str]
    items: list[SessionItemRead] = Field(default_factory=list)
    logged_minutes: int
    total_load: float
    is_open: bool


class PracticeSessionPage(BaseModel):
    meta: PageMeta
    items: list[PracticeSessionRead]


class LoadAlertRead(ORMModel):
    id: uuid.UUID
    week_start: date
    load_total: Decimal
    threshold: Decimal
    severity: LoadSeverity
    message: Optional[str]
    acknowledged_at: Optional[datetime]
    overshoot_ratio: Optional[float]


class StretchWarning(BaseModel):
    piece_id: int
    title: str
    required_cm: Optional[float]
    your_span_cm: float
    advice: str


class WeeklyLoadPoint(BaseModel):
    week_start: str
    load: float


class LoadSummary(BaseModel):
    week_start: str
    load_total: float
    threshold: float
    ratio: Optional[float]
    severity: str
    message: Optional[str]
    minutes_this_week: int
    history: list[WeeklyLoadPoint]
    stretch_warnings: list[StretchWarning]


class LiveFrame(BaseModel):
    bpm: Optional[float] = Field(default=None, ge=20, le=400)
    accuracy: Optional[float] = Field(default=None, ge=0, le=1)
    tension: Optional[float] = Field(default=None, ge=0, le=1)


class LiveFeedback(BaseModel):
    frame: int
    cues: list[str]
    rolling: dict[str, Optional[float]]


class DrillRead(ORMModel):
    id: uuid.UUID
    passage_id: int
    drill_type: DrillType
    params: Optional[dict[str, Any]]
    musicxml_key: Optional[str]
    created_at: datetime
    label: str
    is_ready: bool
    times_practised: int
    passage: PassageRead


class DrillForgeRequest(BaseModel):
    passage_id: Optional[int] = None
    count: int = Field(default=2, ge=1, le=4)


class PlanStepRead(ORMModel):
    id: uuid.UUID
    step_order: int
    piece_id: Optional[int]
    passage_id: Optional[int]
    instruction: str
    est_days: Optional[int]
    status: PlanStepStatus
    scope_label: str


class PracticePlanRead(ORMModel):
    id: uuid.UUID
    repertoire_entry_id: uuid.UUID
    model: Optional[str]
    rationale: Optional[str]
    created_at: datetime
    steps: list[PlanStepRead] = Field(default_factory=list)
    progress: float
    estimated_days: int


class SightReadingRequest(BaseModel):
    style_composer_id: Optional[int] = None
    target_piece_id: Optional[int] = None
    technique_id: Optional[int] = None
    difficulty: Optional[float] = Field(default=None, ge=1, le=10)


class SightReadingRead(ORMModel):
    id: uuid.UUID
    style_composer_id: Optional[int]
    target_piece_id: Optional[int]
    technique_id: Optional[int]
    difficulty: Optional[Decimal]
    seed: int
    musicxml_key: Optional[str]
    notation: Optional[dict[str, Any]]
    self_score: Optional[int]
    attempted_at: Optional[datetime]
    style_label: str


class SightReadingScore(BaseModel):
    self_score: int = Field(ge=1, le=5)


class PolyrhythmRecord(BaseModel):
    ratio_left: int = Field(ge=1, le=16)
    ratio_right: int = Field(ge=1, le=16)
    bpm: int = Field(ge=20, le=300)
    offsets_ms: list[float] = Field(default_factory=list, max_length=512)


class PolyrhythmAttemptRead(ORMModel):
    id: uuid.UUID
    ratio_left: int
    ratio_right: int
    bpm: int
    mean_offset_ms: Optional[Decimal]
    accuracy_score: Optional[Decimal]
    created_at: datetime
    ratio_label: str
    is_clean: bool
    rushing: Optional[bool]


class PerformanceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    event_date: Optional[date] = None
    venue: Optional[str] = Field(default=None, max_length=120)


class PerformanceUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    event_date: Optional[date] = None
    venue: Optional[str] = Field(default=None, max_length=120)


class ProgramItemRead(ORMModel):
    program_order: int
    repertoire_entry_id: uuid.UUID
    repertoire_entry: RepertoireEntryRead


class PerformanceRead(ORMModel):
    id: uuid.UUID
    title: str
    event_date: Optional[date]
    venue: Optional[str]
    program: list[ProgramItemRead] = Field(default_factory=list)
    days_until: Optional[int]
    total_duration_sec: int


class ProgramSet(BaseModel):
    repertoire_entry_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)


class ReadinessScoreRead(ORMModel):
    id: uuid.UUID
    repertoire_entry_id: uuid.UUID
    audio_submission_id: Optional[uuid.UUID]
    overall_score: Optional[Decimal]
    tempo_stability: Optional[Decimal]
    restart_count: int
    memory_slip_count: int
    created_at: datetime
    verdict: str
    is_clean_run: bool


class ProgramReadinessItem(BaseModel):
    program_order: int
    repertoire_entry_id: str
    title: str
    status: str
    overall_score: Optional[float]
    verdict: str
    restart_count: Optional[int]
    memory_slip_count: Optional[int]
    duration_sec: Optional[int]


class PerformanceReadiness(BaseModel):
    performance_id: str
    title: str
    event_date: Optional[str]
    days_until: Optional[int]
    total_duration_sec: int
    program: list[ProgramReadinessItem]
    average_score: Optional[float]
    unscored_count: int
    weakest_link: Optional[ProgramReadinessItem]
    verdict: str


class WalletRead(ORMModel):
    xp: int
    gold: int
    lifetime_xp: int
    lifetime_gold: int
    level: int
    xp_into_level: int
    xp_for_next_level: int
    level_progress: float


class LedgerEntryRead(ORMModel):
    id: uuid.UUID
    delta_xp: int
    delta_gold: int
    reason: LedgerReason
    detail: Optional[str]
    ref_type: Optional[str]
    created_at: datetime


class AchievementRead(BaseModel):
    id: int
    code: str
    name: str
    description: str
    xp_reward: int
    gold_reward: int
    earned: bool
    earned_at: Optional[datetime] = None


class CosmeticRead(BaseModel):
    id: int
    code: str
    kind: CosmeticKind
    name: str
    description: Optional[str]
    price_gold: int
    min_level: int
    payload: Optional[dict[str, Any]]
    owned: bool
    equipped: bool
    affordable: bool
    unlocked: bool


class LoadoutRead(BaseModel):
    star_color: Optional[dict[str, Any]] = None
    glow: Optional[dict[str, Any]] = None
    nebula: Optional[dict[str, Any]] = None
    link_style: Optional[dict[str, Any]] = None


class ProfileSummary(BaseModel):
    wallet: WalletRead
    loadout: LoadoutRead
    achievements_earned: int
    achievements_total: int


class PathwayStep(BaseModel):
    order: int
    piece: PieceDetail
    score: float
    gap: float
    shared_techniques: list[str]
    rationale: str
    owned: bool


class PathwayResponse(BaseModel):
    target: PieceDetail
    comfort_ceiling: float
    target_difficulty: float
    gap: float
    out_of_reach: bool
    steps: list[PathwayStep]


class PathwayAdopt(BaseModel):
    piece_ids: list[int] = Field(default_factory=list, max_length=8)
    include_target: bool = True


class PathwayAdopted(BaseModel):
    created: list[RepertoireEntryRead]
    skipped: int
    message: str


class GradingGate(BaseModel):
    requires_grading: bool
    threshold: float
    pass_score: float
    best_score: Optional[float]
    unlocked: bool


class ReadinessOutcome(ReadinessScoreRead):
    promoted: bool = False
    reward_xp: int = 0
    reward_gold: int = 0


class ComposerProfile(BaseModel):
    id: int
    name: str
    nationality: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    lifespan: str = ""
    byline: str = ""
    bio: Optional[str] = None
    fun_fact: Optional[str] = None
    signature_sound: Optional[str] = None
    era: Optional[str] = None


class SectionRead(BaseModel):
    id: int
    label: Optional[str] = None
    start_measure: int
    end_measure: int
    measure_span: str
    length: int
    difficulty_score: Optional[Decimal] = None
    description: Optional[str] = None
    practice_cue: Optional[str] = None
    techniques: list[str] = Field(default_factory=list)


class TechniqueBreakdown(BaseModel):
    id: int
    name: str
    category: TechniqueCategory
    weight: Decimal
    load_factor: Decimal
    description: Optional[str] = None
    mechanic: Optional[str] = None
    common_fault: Optional[str] = None
    mastery_tier: str = "unranked"
    mastery_color: str = "amber"


class LoadProfileRead(BaseModel):
    octave_density: Optional[Decimal] = None
    max_stretch_semitones: Optional[int] = None
    max_stretch_cm: Optional[float] = None
    repeated_chord_density: Optional[Decimal] = None
    notes_per_second_peak: Optional[Decimal] = None
    load_index: Optional[Decimal] = None


class MovementStub(BaseModel):
    id: int
    title: str
    movement_number: Optional[int] = None
    difficulty_score: Optional[Decimal] = None
    duration_label: str = ""


class PieceStub(BaseModel):
    id: int
    title: str


class PieceOverview(BaseModel):
    id: int
    title: str
    catalog_number: Optional[str] = None
    key_signature: Optional[str] = None
    year_composed: Optional[int] = None
    tempo_marking: Optional[str] = None
    difficulty_score: Optional[Decimal] = None
    mechanical_load: Optional[Decimal] = None
    personalized_difficulty: Optional[Decimal] = None
    difficulty_band: str
    syllabus_grade: Optional[str] = None
    requires_verification: bool = False
    is_custom: bool = False
    external_source: Optional[str] = None
    duration_sec: Optional[int] = None
    duration_label: str
    genre: Optional[str] = None
    era: Optional[str] = None
    mood: Optional[str] = None
    scene: Optional[str] = None
    historical_note: Optional[str] = None
    fun_fact: Optional[str] = None
    composer: Optional[ComposerProfile] = None
    sections: list[SectionRead] = Field(default_factory=list)
    techniques: list[TechniqueBreakdown] = Field(default_factory=list)
    load_profile: Optional[LoadProfileRead] = None
    movements: list[MovementStub] = Field(default_factory=list)
    parent_piece: Optional[PieceStub] = None


class LinkEndpoint(BaseModel):
    id: int
    title: str
    composer: Optional[str] = None
    difficulty_score: Optional[Decimal] = None
    era: Optional[str] = None
    genre: Optional[str] = None


class SharedTechnique(BaseModel):
    id: int
    name: str
    category: TechniqueCategory
    mechanic: Optional[str] = None
    common_fault: Optional[str] = None
    load_factor: Decimal
    source_weight: Decimal
    target_weight: Decimal
    pair_weight: float


class SharedSection(BaseModel):
    piece_id: int
    piece_title: str
    label: Optional[str] = None
    measure_span: str
    difficulty_score: Optional[Decimal] = None
    description: Optional[str] = None
    techniques: list[str] = Field(default_factory=list)


class LinkSummary(BaseModel):
    link_type: LinkType
    source: LinkEndpoint
    target: LinkEndpoint
    headline: str
    summary: str
    curated: bool = False
    shared_techniques: list[SharedTechnique] = Field(default_factory=list)
    shared_sections: list[SharedSection] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

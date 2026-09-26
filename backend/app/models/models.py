from __future__ import annotations

import enum
import math
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EMBEDDING_DIM = 64


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class SelfLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    PROFESSIONAL = "professional"


class ProfileVisibility(str, enum.Enum):
    PRIVATE = "private"
    FRIENDS = "friends"
    PUBLIC = "public"


class FriendshipStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class GenreFamily(str, enum.Enum):
    CLASSICAL = "classical"
    JAZZ = "jazz"
    POP = "pop"
    FILM_GAME = "film_game"
    FOLK = "folk"
    OTHER = "other"


class TechniqueCategory(str, enum.Enum):
    DEXTERITY = "dexterity"
    DOUBLE_NOTES = "double_notes"
    OCTAVES = "octaves"
    LEAPS = "leaps"
    CHORDS = "chords"
    REPEATED_NOTES = "repeated_notes"
    TRILLS = "trills"
    STRETCHES = "stretches"
    POLYRHYTHM = "polyrhythm"
    VOICING = "voicing"
    PEDALING = "pedaling"
    ENDURANCE = "endurance"


class PassageSource(str, enum.Enum):
    CATALOG = "catalog"
    ANALYZER = "analyzer"
    USER = "user"


class PrerequisiteSource(str, enum.Enum):
    CURATED = "curated"
    COMPUTED = "computed"
    AI = "ai"


class LinkType(str, enum.Enum):
    COMPOSER = "composer"
    TECHNIQUE = "technique"
    ERA_GENRE = "era_genre"


class RepertoireStatus(str, enum.Enum):
    WISHLIST = "wishlist"
    LEARNING = "learning"
    POLISHING = "polishing"
    PERFORMANCE_READY = "performance_ready"
    RETIRED = "retired"


class SubmissionType(str, enum.Enum):
    TEXT = "text"
    PDF = "pdf"
    AUDIO = "audio"


class ProcessingStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class GenerationStatus(str, enum.Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class FlaggedBy(str, enum.Enum):
    AI = "ai"
    USER = "user"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
    }

    def __repr__(self) -> str:
        pk = ", ".join(f"{c.key}={getattr(self, c.key, None)!r}" for c in self.__mapper__.primary_key)
        return f"<{type(self).__name__} {pk}>"


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class IntPrimaryKeyMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(80))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    years_playing: Mapped[Optional[int]] = mapped_column(SmallInteger)
    self_level: Mapped[Optional[SelfLevel]] = mapped_column(pg_enum(SelfLevel, "self_level"))
    hand_span_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    nudge_after_days: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    profile_visibility: Mapped[ProfileVisibility] = mapped_column(
        pg_enum(ProfileVisibility, "profile_visibility"),
        default=ProfileVisibility.FRIENDS,
        server_default=ProfileVisibility.FRIENDS.value,
    )
    tier_quiz_completed_at: Mapped[Optional[datetime]]

    sent_friend_requests: Mapped[list[Friendship]] = relationship(
        back_populates="requester",
        foreign_keys="Friendship.requester_id",
        cascade="all, delete-orphan",
    )
    received_friend_requests: Mapped[list[Friendship]] = relationship(
        back_populates="addressee",
        foreign_keys="Friendship.addressee_id",
        cascade="all, delete-orphan",
    )
    repertoire: Mapped[list[RepertoireEntry]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_pieces: Mapped[list[Piece]] = relationship(back_populates="creator")

    @property
    def name(self) -> str:
        return self.display_name or self.email.split("@")[0]

    @property
    def is_public(self) -> bool:
        return self.profile_visibility == ProfileVisibility.PUBLIC

    @property
    def friends(self) -> list[User]:
        sent = [f.addressee for f in self.sent_friend_requests if f.is_accepted]
        received = [f.requester for f in self.received_friend_requests if f.is_accepted]
        return sent + received

    @property
    def top_ten(self) -> list[RepertoireEntry]:
        ranked = [e for e in self.repertoire if e.is_top_ten]
        return sorted(ranked, key=lambda e: e.top_ten_rank or 99)


class Friendship(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="uq_friendships_pair"),
        CheckConstraint("requester_id <> addressee_id", name="not_self"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addressee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[FriendshipStatus] = mapped_column(
        pg_enum(FriendshipStatus, "friendship_status"),
        default=FriendshipStatus.PENDING,
        server_default=FriendshipStatus.PENDING.value,
    )
    responded_at: Mapped[Optional[datetime]]

    requester: Mapped[User] = relationship(back_populates="sent_friend_requests", foreign_keys=[requester_id])
    addressee: Mapped[User] = relationship(back_populates="received_friend_requests", foreign_keys=[addressee_id])

    @property
    def is_accepted(self) -> bool:
        return self.status == FriendshipStatus.ACCEPTED

    def other(self, user: User) -> User:
        return self.addressee if user.id == self.requester_id else self.requester


class Era(IntPrimaryKeyMixin, Base):
    __tablename__ = "eras"

    name: Mapped[str] = mapped_column(String(40), unique=True)
    start_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    end_year: Mapped[Optional[int]] = mapped_column(SmallInteger)

    composers: Mapped[list[Composer]] = relationship(back_populates="era")

    @property
    def span(self) -> str:
        return f"{self.start_year or '?'}–{self.end_year or 'present'}"


class Genre(IntPrimaryKeyMixin, Base):
    __tablename__ = "genres"

    name: Mapped[str] = mapped_column(String(60), unique=True)
    family: Mapped[GenreFamily] = mapped_column(pg_enum(GenreFamily, "genre_family"), default=GenreFamily.CLASSICAL)

    pieces: Mapped[list[Piece]] = relationship(back_populates="genre")


class Composer(IntPrimaryKeyMixin, Base):
    __tablename__ = "composers"

    name: Mapped[str] = mapped_column(String(120), index=True)
    birth_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    death_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    nationality: Mapped[Optional[str]] = mapped_column(String(60))
    era_id: Mapped[Optional[int]] = mapped_column(ForeignKey("eras.id", ondelete="SET NULL"), index=True)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    fun_fact: Mapped[Optional[str]] = mapped_column(Text)
    signature_sound: Mapped[Optional[str]] = mapped_column(Text)

    era: Mapped[Optional[Era]] = relationship(back_populates="composers")
    pieces: Mapped[list[Piece]] = relationship(back_populates="composer")

    @property
    def lifespan(self) -> str:
        if self.birth_year is None:
            return ""
        return f"{self.birth_year}–{self.death_year or ''}"

    @property
    def byline(self) -> str:
        bits = [self.name]
        if self.nationality:
            bits.append(self.nationality)
        if self.birth_year:
            bits.append(self.lifespan)
        return " · ".join(bits)


class Technique(IntPrimaryKeyMixin, Base):
    __tablename__ = "techniques"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[TechniqueCategory] = mapped_column(pg_enum(TechniqueCategory, "technique_category"))
    parent_technique_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("techniques.id", ondelete="SET NULL"), index=True
    )
    load_factor: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    mechanic: Mapped[Optional[str]] = mapped_column(Text)
    common_fault: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIM))

    parent: Mapped[Optional[Technique]] = relationship(back_populates="children", remote_side="Technique.id")
    children: Mapped[list[Technique]] = relationship(back_populates="parent")
    piece_links: Mapped[list[PieceTechnique]] = relationship(back_populates="technique")

    @property
    def lineage(self) -> list[str]:
        chain, node = [], self
        while node is not None:
            chain.append(node.name)
            node = node.parent
        return list(reversed(chain))


class Piece(IntPrimaryKeyMixin, Base):
    __tablename__ = "pieces"
    __table_args__ = (
        CheckConstraint("difficulty_score BETWEEN 0 AND 100", name="difficulty_range"),
        CheckConstraint("mechanical_load BETWEEN 0 AND 100", name="mechanical_load_range"),
    )

    title: Mapped[str] = mapped_column(String(200), index=True)
    composer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("composers.id", ondelete="SET NULL"), index=True)
    genre_id: Mapped[Optional[int]] = mapped_column(ForeignKey("genres.id", ondelete="SET NULL"), index=True)
    catalog_number: Mapped[Optional[str]] = mapped_column(String(40))
    key_signature: Mapped[Optional[str]] = mapped_column(String(20))
    year_composed: Mapped[Optional[int]] = mapped_column(SmallInteger)
    difficulty_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1))
    mechanical_load: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1))
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer)
    parent_piece_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    movement_number: Mapped[Optional[int]] = mapped_column(SmallInteger)
    is_user_created: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    technique_vector: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIM))
    tempo_marking: Mapped[Optional[str]] = mapped_column(String(80))
    mood: Mapped[Optional[str]] = mapped_column(String(80))
    scene: Mapped[Optional[str]] = mapped_column(Text)
    historical_note: Mapped[Optional[str]] = mapped_column(Text)
    fun_fact: Mapped[Optional[str]] = mapped_column(Text)
    syllabus_grade: Mapped[Optional[str]] = mapped_column(String(40))
    external_source: Mapped[Optional[str]] = mapped_column(String(40))
    external_ref: Mapped[Optional[str]] = mapped_column(String(120))
    metadata_generated_at: Mapped[Optional[datetime]]
    metadata_generation_model: Mapped[Optional[str]] = mapped_column(String(60))
    custom_style: Mapped[Optional[dict[str, Any]]]

    composer: Mapped[Optional[Composer]] = relationship(back_populates="pieces")
    genre: Mapped[Optional[Genre]] = relationship(back_populates="pieces")
    creator: Mapped[Optional[User]] = relationship(back_populates="created_pieces")
    parent_piece: Mapped[Optional[Piece]] = relationship(back_populates="movements", remote_side="Piece.id")
    movements: Mapped[list[Piece]] = relationship(
        back_populates="parent_piece", order_by="Piece.movement_number", cascade="all, delete-orphan"
    )
    technique_links: Mapped[list[PieceTechnique]] = relationship(
        back_populates="piece", cascade="all, delete-orphan"
    )
    load_profile: Mapped[Optional[PieceLoadProfile]] = relationship(
        back_populates="piece", uselist=False, cascade="all, delete-orphan"
    )
    passages: Mapped[list[Passage]] = relationship(
        back_populates="piece", order_by="Passage.start_measure", cascade="all, delete-orphan"
    )
    prerequisite_links: Mapped[list[PiecePrerequisite]] = relationship(
        back_populates="target_piece",
        foreign_keys="PiecePrerequisite.target_piece_id",
        cascade="all, delete-orphan",
    )
    unlocks_links: Mapped[list[PiecePrerequisite]] = relationship(
        back_populates="prerequisite_piece",
        foreign_keys="PiecePrerequisite.prerequisite_piece_id",
        cascade="all, delete-orphan",
    )

    @property
    def is_movement(self) -> bool:
        return self.parent_piece_id is not None

    @property
    def display_title(self) -> str:
        parts = [self.title]
        if self.catalog_number:
            parts.append(self.catalog_number)
        label = ", ".join(parts)
        return f"{self.composer.name}: {label}" if self.composer else label

    @property
    def technique_weights(self) -> dict[str, float]:
        return {link.technique.name: float(link.weight) for link in self.technique_links}

    @property
    def prerequisites(self) -> list[Piece]:
        ranked = sorted(self.prerequisite_links, key=lambda l: l.overlap_score or 0, reverse=True)
        return [link.prerequisite_piece for link in ranked]

    @property
    def era_name(self) -> Optional[str]:
        if self.composer and self.composer.era:
            return self.composer.era.name
        return None

    @property
    def duration_label(self) -> str:
        if not self.duration_sec:
            return "unknown"
        minutes, seconds = divmod(self.duration_sec, 60)
        if minutes and seconds:
            return f"{minutes} min {seconds} sec"
        if minutes:
            return f"{minutes} min"
        return f"{seconds} sec"

    @property
    def hardest_techniques(self) -> list[PieceTechnique]:
        return sorted(
            self.technique_links,
            key=lambda link: (float(link.weight) * float(link.technique.load_factor)),
            reverse=True,
        )

    @property
    def hardest_passages(self) -> list[Passage]:
        scored = [p for p in self.passages if p.difficulty_score is not None]
        return sorted(scored, key=lambda p: p.difficulty_score, reverse=True)

    @property
    def is_custom(self) -> bool:
        return self.is_user_created

    @property
    def requires_verification(self) -> bool:
        return self.difficulty_score is not None and self.difficulty_score >= VERIFICATION_DIFFICULTY_THRESHOLD

    @property
    def has_generated_metadata(self) -> bool:
        return self.metadata_generated_at is not None


class PieceTechnique(Base):
    __tablename__ = "piece_techniques"
    __table_args__ = (CheckConstraint("weight BETWEEN 0 AND 1", name="weight_range"),)

    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), primary_key=True)
    technique_id: Mapped[int] = mapped_column(ForeignKey("techniques.id", ondelete="CASCADE"), primary_key=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2))

    piece: Mapped[Piece] = relationship(back_populates="technique_links")
    technique: Mapped[Technique] = relationship(back_populates="piece_links")


class PieceLoadProfile(Base):
    __tablename__ = "piece_load_profiles"

    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), primary_key=True)
    octave_density: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    max_stretch_semitones: Mapped[Optional[int]] = mapped_column(SmallInteger)
    repeated_chord_density: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    notes_per_second_peak: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    load_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))

    piece: Mapped[Piece] = relationship(back_populates="load_profile")

    def max_stretch_cm(self, key_width_cm: float = 2.35) -> Optional[float]:
        if self.max_stretch_semitones is None:
            return None
        return round(self.max_stretch_semitones * 7 / 12 * key_width_cm, 1)

    def exceeds_span(self, hand_span_cm: Optional[Decimal]) -> bool:
        stretch = self.max_stretch_cm()
        return stretch is not None and hand_span_cm is not None and stretch > float(hand_span_cm)


class Passage(IntPrimaryKeyMixin, Base):
    __tablename__ = "passages"
    __table_args__ = (CheckConstraint("end_measure >= start_measure", name="measure_order"),)

    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    start_measure: Mapped[int] = mapped_column(Integer)
    end_measure: Mapped[int] = mapped_column(Integer)
    label: Mapped[Optional[str]] = mapped_column(String(80))
    difficulty_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1))
    source: Mapped[PassageSource] = mapped_column(pg_enum(PassageSource, "passage_source"), default=PassageSource.USER)
    description: Mapped[Optional[str]] = mapped_column(Text)
    practice_cue: Mapped[Optional[str]] = mapped_column(Text)

    piece: Mapped[Piece] = relationship(back_populates="passages")
    technique_links: Mapped[list[PassageTechnique]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[PassageAssessment]] = relationship(back_populates="passage")

    @property
    def measure_span(self) -> str:
        if self.start_measure == self.end_measure:
            return f"bar {self.start_measure}"
        return f"bars {self.start_measure}–{self.end_measure}"

    @property
    def length(self) -> int:
        return self.end_measure - self.start_measure + 1


class PassageTechnique(Base):
    __tablename__ = "passage_techniques"
    __table_args__ = (CheckConstraint("weight BETWEEN 0 AND 1", name="weight_range"),)

    passage_id: Mapped[int] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"), primary_key=True)
    technique_id: Mapped[int] = mapped_column(ForeignKey("techniques.id", ondelete="CASCADE"), primary_key=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2))

    passage: Mapped[Passage] = relationship(back_populates="technique_links")
    technique: Mapped[Technique] = relationship()


class PiecePrerequisite(IntPrimaryKeyMixin, Base):
    __tablename__ = "piece_prerequisites"
    __table_args__ = (
        UniqueConstraint("target_piece_id", "prerequisite_piece_id", name="uq_piece_prerequisites_pair"),
        CheckConstraint("target_piece_id <> prerequisite_piece_id", name="not_self"),
    )

    target_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    prerequisite_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    overlap_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    source: Mapped[PrerequisiteSource] = mapped_column(
        pg_enum(PrerequisiteSource, "prerequisite_source"), default=PrerequisiteSource.COMPUTED
    )
    rationale: Mapped[Optional[str]] = mapped_column(Text)

    target_piece: Mapped[Piece] = relationship(back_populates="prerequisite_links", foreign_keys=[target_piece_id])
    prerequisite_piece: Mapped[Piece] = relationship(
        back_populates="unlocks_links", foreign_keys=[prerequisite_piece_id]
    )


class PieceLinkNote(IntPrimaryKeyMixin, Base):
    __tablename__ = "piece_link_notes"
    __table_args__ = (
        UniqueConstraint("low_piece_id", "high_piece_id", "link_type", name="uq_piece_link_notes_edge"),
        CheckConstraint("low_piece_id < high_piece_id", name="ordered_pair"),
    )

    low_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    high_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    link_type: Mapped[LinkType] = mapped_column(pg_enum(LinkType, "link_type"))
    headline: Mapped[Optional[str]] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)

    low_piece: Mapped[Piece] = relationship(foreign_keys=[low_piece_id])
    high_piece: Mapped[Piece] = relationship(foreign_keys=[high_piece_id])

    @staticmethod
    def order_pair(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)


class RepertoireEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "repertoire_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "piece_id", name="uq_repertoire_entries_user_piece"),
        CheckConstraint("top_ten_rank IS NULL OR top_ten_rank BETWEEN 1 AND 10", name="top_ten_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="RESTRICT"), index=True)
    status: Mapped[RepertoireStatus] = mapped_column(
        pg_enum(RepertoireStatus, "repertoire_status"),
        default=RepertoireStatus.LEARNING,
        server_default=RepertoireStatus.LEARNING.value,
    )
    is_top_ten: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    top_ten_rank: Mapped[Optional[int]] = mapped_column(SmallInteger)
    current_tempo_bpm: Mapped[Optional[int]] = mapped_column(SmallInteger)
    target_tempo_bpm: Mapped[Optional[int]] = mapped_column(SmallInteger)
    started_on: Mapped[Optional[date]] = mapped_column(Date)
    completed_on: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_practiced_at: Mapped[Optional[datetime]]

    user: Mapped[User] = relationship(back_populates="repertoire")
    piece: Mapped[Piece] = relationship()
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="repertoire_entry", cascade="all, delete-orphan", order_by="Submission.created_at"
    )

    @property
    def tempo_progress(self) -> Optional[float]:
        if not self.current_tempo_bpm or not self.target_tempo_bpm:
            return None
        return round(min(self.current_tempo_bpm / self.target_tempo_bpm, 1.0), 3)

    @property
    def is_active(self) -> bool:
        return self.status in {RepertoireStatus.LEARNING, RepertoireStatus.POLISHING}

    @property
    def days_in_progress(self) -> Optional[int]:
        if self.started_on is None:
            return None
        end = self.completed_on or date.today()
        return (end - self.started_on).days

    @property
    def needs_verification(self) -> bool:
        return bool(self.piece and self.piece.requires_verification) and not self.is_verified

    @property
    def decay_level(self) -> float:
        if self.last_practiced_at is None:
            return 0.0
        elapsed_days = (datetime.now(timezone.utc) - self.last_practiced_at).total_seconds() / 86400
        if elapsed_days <= 0:
            return 0.0
        difficulty = float(self.piece.difficulty_score) if self.piece and self.piece.difficulty_score else 40.0
        half_life = max(ORBITAL_DECAY_HALF_LIFE_DAYS * (1.4 - difficulty / 200.0), 6.0)
        return round(1.0 - 0.5 ** (elapsed_days / half_life), 3)

    @property
    def is_frozen(self) -> bool:
        return self.decay_level >= 0.85


class Submission(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "submissions"

    repertoire_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repertoire_entries.id", ondelete="CASCADE"), index=True
    )
    submission_type: Mapped[SubmissionType] = mapped_column(pg_enum(SubmissionType, "submission_type"))
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        pg_enum(ProcessingStatus, "processing_status"),
        default=ProcessingStatus.QUEUED,
        server_default=ProcessingStatus.QUEUED.value,
    )

    repertoire_entry: Mapped[RepertoireEntry] = relationship(back_populates="submissions")
    analyses: Mapped[list[Analysis]] = relationship(back_populates="submission", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_on": "submission_type",
        "polymorphic_abstract": True,
    }

    @property
    def is_processed(self) -> bool:
        return self.processing_status == ProcessingStatus.DONE

    @property
    def latest_analysis(self) -> Optional[Analysis]:
        return max(self.analyses, key=lambda a: a.created_at, default=None)

    def mark(self, status: ProcessingStatus) -> None:
        self.processing_status = status


class TextSubmission(Submission):
    __tablename__ = "text_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        "submission_id", ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    body: Mapped[str] = mapped_column(Text)

    __mapper_args__ = {"polymorphic_identity": SubmissionType.TEXT}

    @property
    def word_count(self) -> int:
        return len(self.body.split())


class PdfSubmission(Submission):
    __tablename__ = "pdf_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        "submission_id", ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(SmallInteger)
    musicxml_key: Mapped[Optional[str]] = mapped_column(Text)
    omr_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))

    __mapper_args__ = {"polymorphic_identity": SubmissionType.PDF}

    @property
    def has_musicxml(self) -> bool:
        return self.musicxml_key is not None

    @property
    def needs_review(self) -> bool:
        return self.omr_confidence is not None and self.omr_confidence < Decimal("0.80")


class AudioSubmission(Submission):
    __tablename__ = "audio_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        "submission_id", ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer)
    is_full_run_through: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_verification: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    midi_key: Mapped[Optional[str]] = mapped_column(Text)
    tempo_curve: Mapped[Optional[dict[str, Any]]]
    interpretation: Mapped[Optional[dict[str, Any]]]

    __mapper_args__ = {"polymorphic_identity": SubmissionType.AUDIO}

    @property
    def is_transcribed(self) -> bool:
        return self.midi_key is not None

    @property
    def duration_label(self) -> str:
        if self.duration_sec is None:
            return "--:--"
        minutes, seconds = divmod(self.duration_sec, 60)
        return f"{minutes}:{seconds:02d}"


class Analysis(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "analyses"

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    analyzer_name: Mapped[str] = mapped_column(String(60))
    analyzer_version: Mapped[str] = mapped_column(String(20))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    raw_result: Mapped[Optional[dict[str, Any]]]

    submission: Mapped[Submission] = relationship(back_populates="analyses")
    passage_assessments: Mapped[list[PassageAssessment]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )

    @property
    def weakest_passages(self) -> list[PassageAssessment]:
        scored = [p for p in self.passage_assessments if p.accuracy_score is not None]
        return sorted(scored, key=lambda p: p.accuracy_score)[:3]


class PassageAssessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "passage_assessments"

    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    passage_id: Mapped[int] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    accuracy_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    tempo_stability: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    voicing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    restart_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    memory_slip: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    flagged_by: Mapped[FlaggedBy] = mapped_column(pg_enum(FlaggedBy, "flagged_by"), default=FlaggedBy.AI)

    analysis: Mapped[Analysis] = relationship(back_populates="passage_assessments")
    passage: Mapped[Passage] = relationship(back_populates="assessments")

    @property
    def needs_work(self) -> bool:
        low_accuracy = self.accuracy_score is not None and self.accuracy_score < Decimal("0.85")
        return low_accuracy or self.memory_slip or self.restart_count > 0


class SelfRating(str, enum.Enum):
    STRUGGLE = "struggle"
    NEUTRAL = "neutral"
    STRENGTH = "strength"


class PracticeMode(str, enum.Enum):
    FREE = "free"
    LIVE_LISTENING = "live_listening"
    FORGE_DRILL = "forge_drill"
    SIGHT_READING = "sight_reading"
    POLYRHYTHM = "polyrhythm"


class LoadSeverity(str, enum.Enum):
    INFO = "info"
    CAUTION = "caution"
    REST = "rest"


class RecommendationStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class PlanStepStatus(str, enum.Enum):
    TODO = "todo"
    ACTIVE = "active"
    DONE = "done"


class DrillType(str, enum.Enum):
    RHYTHM_VARIANT = "rhythm_variant"
    TRANSPOSITION = "transposition"
    HANDS_SEPARATE = "hands_separate"
    CORTOT_REDUCTION = "cortot_reduction"
    POLYRHYTHM = "polyrhythm"
    VOICING = "voicing"


class UserGenrePreference(Base):
    __tablename__ = "user_genre_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True)

    user: Mapped[User] = relationship()
    genre: Mapped[Genre] = relationship()


class UserComposerPreference(Base):
    __tablename__ = "user_composer_preferences"
    __table_args__ = (CheckConstraint("rank IS NULL OR rank > 0", name="rank_positive"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    composer_id: Mapped[int] = mapped_column(ForeignKey("composers.id", ondelete="CASCADE"), primary_key=True)
    rank: Mapped[Optional[int]] = mapped_column(SmallInteger)

    user: Mapped[User] = relationship()
    composer: Mapped[Composer] = relationship()


class UserTechniqueProfile(Base):
    __tablename__ = "user_technique_profiles"
    __table_args__ = (
        CheckConstraint("proficiency_score IS NULL OR proficiency_score BETWEEN 0 AND 10", name="proficiency_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    technique_id: Mapped[int] = mapped_column(ForeignKey("techniques.id", ondelete="CASCADE"), primary_key=True)
    self_rating: Mapped[SelfRating] = mapped_column(
        pg_enum(SelfRating, "self_rating"), default=SelfRating.NEUTRAL, server_default=SelfRating.NEUTRAL.value
    )
    proficiency_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship()
    technique: Mapped[Technique] = relationship()

    @property
    def is_weakness(self) -> bool:
        if self.self_rating == SelfRating.STRUGGLE:
            return True
        return self.proficiency_score is not None and self.proficiency_score < Decimal("5.00")

    @property
    def is_strength(self) -> bool:
        if self.self_rating == SelfRating.STRENGTH:
            return True
        return self.proficiency_score is not None and self.proficiency_score >= Decimal("8.00")

    @property
    def mastery_tier(self) -> str:
        if self.proficiency_score is None:
            return "unranked"
        value = float(self.proficiency_score)
        if value >= 8:
            return "S"
        if value >= 6.5:
            return "A"
        if value >= 5:
            return "B"
        if value >= 3:
            return "C"
        return "D"

    @property
    def mastery_color(self) -> str:
        if self.is_strength:
            return "green"
        if self.is_weakness:
            return "red"
        return "amber"


class PracticeSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint("perceived_tension IS NULL OR perceived_tension BETWEEN 1 AND 5", name="tension_range"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="session_order"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[PracticeMode] = mapped_column(
        pg_enum(PracticeMode, "practice_mode"), default=PracticeMode.FREE, server_default=PracticeMode.FREE.value
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    ended_at: Mapped[Optional[datetime]]
    perceived_tension: Mapped[Optional[int]] = mapped_column(SmallInteger)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[User] = relationship()
    items: Mapped[list[SessionItem]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionItem.id"
    )

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def duration_min(self) -> Optional[int]:
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds() // 60)

    @property
    def logged_minutes(self) -> int:
        return sum(item.minutes or 0 for item in self.items)

    @property
    def total_load(self) -> float:
        return round(sum(float(item.load_units or 0) for item in self.items), 2)

    def close(self, tension: Optional[int] = None) -> None:
        self.ended_at = datetime.now(timezone.utc)
        if tension is not None:
            self.perceived_tension = tension


class SessionItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "session_items"
    __table_args__ = (CheckConstraint("minutes IS NULL OR minutes >= 0", name="minutes_non_negative"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True)
    repertoire_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("repertoire_entries.id", ondelete="SET NULL"), index=True
    )
    passage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("passages.id", ondelete="SET NULL"), index=True)
    drill_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("drills.id", ondelete="SET NULL"), index=True)
    minutes: Mapped[Optional[int]] = mapped_column(SmallInteger)
    load_units: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    session: Mapped[PracticeSession] = relationship(back_populates="items")
    repertoire_entry: Mapped[Optional[RepertoireEntry]] = relationship()
    passage: Mapped[Optional[Passage]] = relationship()
    drill: Mapped[Optional[Drill]] = relationship(back_populates="session_items")

    @property
    def target_label(self) -> str:
        if self.drill is not None:
            return self.drill.label
        if self.passage is not None:
            return f"{self.passage.piece.title} {self.passage.measure_span}"
        if self.repertoire_entry is not None:
            return self.repertoire_entry.piece.display_title
        return "free practice"

    def compute_load(self, default_factor: float = 1.0) -> Decimal:
        minutes = self.minutes or 0
        factor = default_factor
        if self.passage is not None:
            weights = [float(link.technique.load_factor) * float(link.weight) for link in self.passage.technique_links]
            if weights:
                factor = sum(weights) / len(weights)
        self.load_units = Decimal(str(round(minutes * factor, 2)))
        return self.load_units


class LoadAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "load_alerts"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_load_alerts_user_week"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    load_total: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    threshold: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    severity: Mapped[LoadSeverity] = mapped_column(
        pg_enum(LoadSeverity, "load_severity"), default=LoadSeverity.INFO, server_default=LoadSeverity.INFO.value
    )
    message: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged_at: Mapped[Optional[datetime]]

    user: Mapped[User] = relationship()

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    @property
    def overshoot_ratio(self) -> Optional[float]:
        if not self.threshold:
            return None
        return round(float(self.load_total) / float(self.threshold), 3)

    def acknowledge(self) -> None:
        self.acknowledged_at = datetime.now(timezone.utc)


class Recommendation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("user_id", "target_piece_id", "recommended_piece_id", name="uq_recommendations_triple"),
        CheckConstraint("target_piece_id <> recommended_piece_id", name="not_self"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    recommended_piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), index=True)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[RecommendationStatus] = mapped_column(
        pg_enum(RecommendationStatus, "recommendation_status"),
        default=RecommendationStatus.SUGGESTED,
        server_default=RecommendationStatus.SUGGESTED.value,
    )

    user: Mapped[User] = relationship()
    target_piece: Mapped[Piece] = relationship(foreign_keys=[target_piece_id])
    recommended_piece: Mapped[Piece] = relationship(foreign_keys=[recommended_piece_id])

    @property
    def is_open(self) -> bool:
        return self.status == RecommendationStatus.SUGGESTED

    @property
    def confidence_label(self) -> str:
        if self.score is None:
            return "unscored"
        value = float(self.score)
        if value >= 0.75:
            return "strong"
        if value >= 0.5:
            return "moderate"
        return "loose"


class PracticePlan(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "practice_plans"

    repertoire_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repertoire_entries.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[Optional[str]] = mapped_column(String(60))
    rationale: Mapped[Optional[str]] = mapped_column(Text)

    repertoire_entry: Mapped[RepertoireEntry] = relationship()
    steps: Mapped[list[PlanStep]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.step_order"
    )

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for step in self.steps if step.status == PlanStepStatus.DONE)
        return round(done / len(self.steps), 3)

    @property
    def current_step(self) -> Optional[PlanStep]:
        active = [s for s in self.steps if s.status == PlanStepStatus.ACTIVE]
        if active:
            return active[0]
        todo = [s for s in self.steps if s.status == PlanStepStatus.TODO]
        return todo[0] if todo else None

    @property
    def estimated_days(self) -> int:
        return sum(step.est_days or 0 for step in self.steps)


class PlanStep(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "plan_steps"
    __table_args__ = (
        UniqueConstraint("plan_id", "step_order", name="uq_plan_steps_order"),
        CheckConstraint("step_order > 0", name="step_order_positive"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practice_plans.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int] = mapped_column(SmallInteger)
    piece_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pieces.id", ondelete="SET NULL"), index=True)
    passage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("passages.id", ondelete="SET NULL"), index=True)
    instruction: Mapped[str] = mapped_column(Text)
    est_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    status: Mapped[PlanStepStatus] = mapped_column(
        pg_enum(PlanStepStatus, "plan_step_status"),
        default=PlanStepStatus.TODO,
        server_default=PlanStepStatus.TODO.value,
    )

    plan: Mapped[PracticePlan] = relationship(back_populates="steps")
    piece: Mapped[Optional[Piece]] = relationship()
    passage: Mapped[Optional[Passage]] = relationship()

    @property
    def is_done(self) -> bool:
        return self.status == PlanStepStatus.DONE

    @property
    def scope_label(self) -> str:
        if self.passage is not None:
            return self.passage.measure_span
        if self.piece is not None:
            return self.piece.display_title
        return "whole work"

    def advance(self) -> None:
        if self.status == PlanStepStatus.TODO:
            self.status = PlanStepStatus.ACTIVE
        elif self.status == PlanStepStatus.ACTIVE:
            self.status = PlanStepStatus.DONE


class Drill(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "drills"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    passage_id: Mapped[int] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    drill_type: Mapped[DrillType] = mapped_column(pg_enum(DrillType, "drill_type"))
    params: Mapped[Optional[dict[str, Any]]]
    musicxml_key: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[User] = relationship()
    passage: Mapped[Passage] = relationship()
    session_items: Mapped[list[SessionItem]] = relationship(back_populates="drill")

    @property
    def label(self) -> str:
        return f"{self.drill_type.value.replace('_', ' ')} on {self.passage.measure_span}"

    @property
    def is_ready(self) -> bool:
        return self.musicxml_key is not None

    @property
    def times_practised(self) -> int:
        return len(self.session_items)


class SightReadingExercise(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sight_reading_exercises"
    __table_args__ = (
        CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 0 AND 10", name="difficulty_range"),
        CheckConstraint("self_score IS NULL OR self_score BETWEEN 1 AND 5", name="self_score_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    style_composer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("composers.id", ondelete="SET NULL"))
    target_piece_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pieces.id", ondelete="SET NULL"))
    technique_id: Mapped[Optional[int]] = mapped_column(ForeignKey("techniques.id", ondelete="SET NULL"))
    difficulty: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1))
    seed: Mapped[int] = mapped_column(BigInteger)
    musicxml_key: Mapped[Optional[str]] = mapped_column(Text)
    notation: Mapped[Optional[dict[str, Any]]]
    self_score: Mapped[Optional[int]] = mapped_column(SmallInteger)
    attempted_at: Mapped[Optional[datetime]]

    user: Mapped[User] = relationship()
    style_composer: Mapped[Optional[Composer]] = relationship()
    target_piece: Mapped[Optional[Piece]] = relationship()
    technique: Mapped[Optional[Technique]] = relationship()

    @property
    def is_attempted(self) -> bool:
        return self.attempted_at is not None

    @property
    def passed(self) -> Optional[bool]:
        if self.self_score is None:
            return None
        return self.self_score >= 4

    @property
    def style_label(self) -> str:
        if self.style_composer is not None:
            return f"in the style of {self.style_composer.name}"
        if self.target_piece is not None:
            return f"preparing {self.target_piece.title}"
        return "general"


class PolyrhythmAttempt(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "polyrhythm_attempts"
    __table_args__ = (
        CheckConstraint("ratio_left > 0 AND ratio_right > 0", name="ratio_positive"),
        CheckConstraint("bpm BETWEEN 20 AND 300", name="bpm_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ratio_left: Mapped[int] = mapped_column(SmallInteger)
    ratio_right: Mapped[int] = mapped_column(SmallInteger)
    bpm: Mapped[int] = mapped_column(SmallInteger)
    mean_offset_ms: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    accuracy_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))

    user: Mapped[User] = relationship()

    @property
    def ratio_label(self) -> str:
        return f"{self.ratio_left}:{self.ratio_right}"

    @property
    def is_clean(self) -> bool:
        return self.accuracy_score is not None and self.accuracy_score >= Decimal("0.900")

    @property
    def rushing(self) -> Optional[bool]:
        if self.mean_offset_ms is None:
            return None
        return self.mean_offset_ms < 0


class Performance(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "performances"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    event_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    venue: Mapped[Optional[str]] = mapped_column(String(120))

    user: Mapped[User] = relationship()
    program: Mapped[list[PerformanceProgram]] = relationship(
        back_populates="performance", cascade="all, delete-orphan", order_by="PerformanceProgram.program_order"
    )

    @property
    def days_until(self) -> Optional[int]:
        if self.event_date is None:
            return None
        return (self.event_date - date.today()).days

    @property
    def is_upcoming(self) -> bool:
        days = self.days_until
        return days is not None and days >= 0

    @property
    def total_duration_sec(self) -> int:
        return sum(item.repertoire_entry.piece.duration_sec or 0 for item in self.program)

    @property
    def unready_pieces(self) -> list[RepertoireEntry]:
        return [
            item.repertoire_entry
            for item in self.program
            if item.repertoire_entry.status != RepertoireStatus.PERFORMANCE_READY
        ]


class PerformanceProgram(Base):
    __tablename__ = "performance_program"
    __table_args__ = (CheckConstraint("program_order > 0", name="program_order_positive"),)

    performance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("performances.id", ondelete="CASCADE"), primary_key=True
    )
    repertoire_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repertoire_entries.id", ondelete="CASCADE"), primary_key=True
    )
    program_order: Mapped[int] = mapped_column(SmallInteger)

    performance: Mapped[Performance] = relationship(back_populates="program")
    repertoire_entry: Mapped[RepertoireEntry] = relationship()


class ReadinessScore(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "readiness_scores"
    __table_args__ = (
        CheckConstraint("overall_score IS NULL OR overall_score BETWEEN 0 AND 100", name="overall_range"),
    )

    repertoire_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repertoire_entries.id", ondelete="CASCADE"), index=True
    )
    audio_submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("audio_submissions.submission_id", ondelete="SET NULL"), index=True
    )
    overall_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1))
    tempo_stability: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    restart_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    memory_slip_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    repertoire_entry: Mapped[RepertoireEntry] = relationship()
    audio_submission: Mapped[Optional[AudioSubmission]] = relationship()

    @property
    def verdict(self) -> str:
        if self.overall_score is None:
            return "unscored"
        value = float(self.overall_score)
        if value >= 85 and self.is_clean_run:
            return "stage ready"
        if value >= 70:
            return "nearly there"
        return "keep building"

    @property
    def is_clean_run(self) -> bool:
        return self.restart_count == 0 and self.memory_slip_count == 0


GRADED_DIFFICULTY_THRESHOLD = Decimal("70.0")
GRADED_PASS_SCORE = Decimal("80.0")
VERIFICATION_DIFFICULTY_THRESHOLD = Decimal("70.0")
ORBITAL_DECAY_HALF_LIFE_DAYS = 21
LEVEL_BASE = 100


def level_for_xp(xp: int) -> int:
    if xp <= 0:
        return 1
    return int((-1 + math.sqrt(1 + (4 * xp) / LEVEL_BASE)) / 2) + 1


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    span = level - 1
    return LEVEL_BASE * span * (span + 1)


class LedgerReason(str, enum.Enum):
    PIECE_LEARNED = "piece_learned"
    GRADED_PERFORMANCE = "graded_performance"
    PRACTICE_SESSION = "practice_session"
    DRILL_FORGED = "drill_forged"
    PATHWAY_STARTED = "pathway_started"
    ACHIEVEMENT = "achievement"
    PURCHASE = "purchase"
    ADJUSTMENT = "adjustment"
    STREAK_BONUS = "streak_bonus"


class CosmeticKind(str, enum.Enum):
    STAR_COLOR = "star_color"
    GLOW = "glow"
    NEBULA = "nebula"
    LINK_STYLE = "link_style"


class Wallet(CreatedAtMixin, Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("gold >= 0", name="gold_non_negative"),
        CheckConstraint("xp >= 0", name="xp_non_negative"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    gold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lifetime_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lifetime_gold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship()

    @property
    def level(self) -> int:
        return level_for_xp(self.xp)

    @property
    def level_floor(self) -> int:
        return xp_for_level(self.level)

    @property
    def level_ceiling(self) -> int:
        return xp_for_level(self.level + 1)

    @property
    def xp_into_level(self) -> int:
        return self.xp - self.level_floor

    @property
    def xp_for_next_level(self) -> int:
        return max(self.level_ceiling - self.xp, 0)

    @property
    def level_progress(self) -> float:
        span = self.level_ceiling - self.level_floor
        if span <= 0:
            return 0.0
        return round(self.xp_into_level / span, 3)


class LedgerEntry(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ledger_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    delta_gold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reason: Mapped[LedgerReason] = mapped_column(pg_enum(LedgerReason, "ledger_reason"))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    ref_type: Mapped[Optional[str]] = mapped_column(String(40))
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))

    user: Mapped[User] = relationship()

    @property
    def is_credit(self) -> bool:
        return self.delta_gold >= 0 and self.delta_xp >= 0


class Achievement(IntPrimaryKeyMixin, Base):
    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    gold_reward: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"), primary_key=True
    )
    earned_at: Mapped[datetime] = mapped_column(server_default=func.now())

    achievement: Mapped[Achievement] = relationship()


class Cosmetic(IntPrimaryKeyMixin, Base):
    __tablename__ = "cosmetics"
    __table_args__ = (CheckConstraint("price_gold >= 0", name="price_non_negative"),)

    code: Mapped[str] = mapped_column(String(60), unique=True)
    kind: Mapped[CosmeticKind] = mapped_column(pg_enum(CosmeticKind, "cosmetic_kind"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    price_gold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    min_level: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    payload: Mapped[Optional[dict[str, Any]]]
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    @property
    def is_free(self) -> bool:
        return self.price_gold == 0


class UserCosmetic(Base):
    __tablename__ = "user_cosmetics"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    cosmetic_id: Mapped[int] = mapped_column(ForeignKey("cosmetics.id", ondelete="CASCADE"), primary_key=True)
    purchased_at: Mapped[datetime] = mapped_column(server_default=func.now())
    equipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    cosmetic: Mapped[Cosmetic] = relationship()


class AIGeneration(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_generations"
    __table_args__ = (UniqueConstraint("purpose", "subject_key", name="uq_ai_generations_subject"),)

    purpose: Mapped[str] = mapped_column(String(40))
    subject_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[GenerationStatus] = mapped_column(
        pg_enum(GenerationStatus, "generation_status"), default=GenerationStatus.RUNNING
    )
    model: Mapped[Optional[str]] = mapped_column(String(60))
    output: Mapped[Optional[dict[str, Any]]]
    error: Mapped[Optional[str]] = mapped_column(Text)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completed_at: Mapped[Optional[datetime]]

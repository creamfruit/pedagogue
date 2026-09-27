from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.models.models import (
    Composer,
    LedgerEntry,
    LedgerReason,
    MeteorShower,
    MeteorShowerPiece,
    Piece,
    RepertoireEntry,
    RepertoireStatus,
    User,
)
from app.schemas.schemas import RepertoireEntryCreate
from app.services.onboarding import BaseService

DEFAULT_HOURS = 48
MAX_HOURS = 24 * 7
MIN_PIECES = 3
MAX_PIECES = 8
DEFAULT_COUNT = 5
CATCH_REF = "meteor_catch"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def spread_pick(candidates: Sequence[int], count: int, seed: str) -> list[int]:
    if len(candidates) <= count:
        return list(candidates)
    offset = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 1000 / 1000
    step = len(candidates) / count
    picks: list[int] = []
    for index in range(count):
        position = min(int((index + offset) * step), len(candidates) - 1)
        while candidates[position] in picks:
            position = (position + 1) % len(candidates)
        picks.append(candidates[position])
    return picks


def shower_window(shower: MeteorShower, now: datetime) -> str:
    if now < shower.starts_at:
        return "upcoming"
    if now >= shower.ends_at:
        return "over"
    return "active"


def piece_card(piece: Piece) -> dict:
    return {
        "id": piece.id,
        "title": piece.title,
        "composer": piece.composer.name if piece.composer else None,
        "era": piece.composer.era.name if piece.composer and piece.composer.era else None,
        "difficulty": float(piece.difficulty_score) if piece.difficulty_score is not None else None,
    }


def shower_summary(shower: MeteorShower, now: datetime) -> dict:
    return {
        "id": shower.id,
        "name": shower.name,
        "description": shower.description,
        "starts_at": shower.starts_at.isoformat(),
        "ends_at": shower.ends_at.isoformat(),
        "window": shower_window(shower, now),
        "seconds_left": max(0, int((shower.ends_at - now).total_seconds())),
        "seconds_to_start": max(0, int((shower.starts_at - now).total_seconds())),
        "catch_xp": shower.catch_xp,
        "catch_gold": shower.catch_gold,
        "learn_multiplier": float(shower.learn_multiplier),
    }


class MeteorService(BaseService):
    def query(self):
        return select(MeteorShower).options(
            selectinload(MeteorShower.pieces)
            .selectinload(MeteorShowerPiece.piece)
            .selectinload(Piece.composer)
            .selectinload(Composer.era)
        )

    async def get(self, shower_id: int) -> Optional[MeteorShower]:
        return (await self.session.execute(self.query().where(MeteorShower.id == shower_id))).scalar_one_or_none()

    async def active(self, now: Optional[datetime] = None) -> Optional[MeteorShower]:
        now = now or utcnow()
        stmt = self.query().where(MeteorShower.starts_at <= now, MeteorShower.ends_at > now).order_by(MeteorShower.starts_at)
        return (await self.session.execute(stmt)).scalars().first()

    async def upcoming(self, now: Optional[datetime] = None) -> Optional[MeteorShower]:
        now = now or utcnow()
        stmt = self.query().where(MeteorShower.starts_at > now).order_by(MeteorShower.starts_at)
        return (await self.session.execute(stmt)).scalars().first()

    async def overlaps(self, starts_at: datetime, ends_at: datetime) -> bool:
        stmt = select(func.count()).select_from(MeteorShower).where(
            MeteorShower.starts_at < ends_at, MeteorShower.ends_at > starts_at
        )
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def view(self, user: User, now: Optional[datetime] = None) -> dict:
        now = now or utcnow()
        shower = await self.active(now)
        upcoming = await self.upcoming(now)
        active = None
        if shower:
            entries = {
                entry.piece_id: entry
                for entry in (
                    await self.session.execute(
                        select(RepertoireEntry).where(
                            RepertoireEntry.user_id == user.id,
                            RepertoireEntry.piece_id.in_([link.piece_id for link in shower.pieces] or [0]),
                        )
                    )
                ).scalars().all()
            }
            pieces = []
            for link in shower.pieces:
                entry = entries.get(link.piece_id)
                state = "open" if entry is None else "caught" if entry.meteor_shower_id == shower.id else "yours"
                pieces.append({**piece_card(link.piece), "state": state, "entry_id": str(entry.id) if entry else None})
            active = {
                **shower_summary(shower, now),
                "pieces": pieces,
                "caught": sum(1 for piece in pieces if piece["state"] == "caught"),
                "open": sum(1 for piece in pieces if piece["state"] == "open"),
            }
        return {
            "now": now.isoformat(),
            "active": active,
            "upcoming": shower_summary(upcoming, now) if upcoming else None,
        }

    async def catch(self, user: User, shower_id: int, piece_id: int, now: Optional[datetime] = None) -> dict:
        from app.services.economy import EconomyService
        from app.services.repertoire import RepertoireService

        shower = await self.active(now)
        if shower is None or shower.id != shower_id:
            raise PermissionError("that meteor shower has passed")
        if piece_id not in {link.piece_id for link in shower.pieces}:
            raise LookupError("that piece isn't part of this meteor shower")
        repertoire = RepertoireService(self.session)
        entry = await repertoire.create(user, RepertoireEntryCreate(piece_id=piece_id, status=RepertoireStatus.LEARNING))
        entry.meteor_shower_id = shower.id
        ref = f"{shower.id}:{piece_id}"
        already = (
            await self.session.execute(
                select(LedgerEntry.id).where(
                    LedgerEntry.user_id == user.id,
                    LedgerEntry.reason == LedgerReason.METEOR_CATCH,
                    LedgerEntry.ref_id == ref,
                )
            )
        ).first()
        awarded = None
        if already is None:
            awarded = await EconomyService(self.session).award(
                user,
                shower.catch_xp,
                shower.catch_gold,
                LedgerReason.METEOR_CATCH,
                detail=f"caught {entry.piece.title} in {shower.name}",
                ref_type=CATCH_REF,
                ref_id=ref,
            )
        await self.session.flush()
        return {
            "entry_id": str(entry.id),
            "xp": awarded.delta_xp if awarded else 0,
            "gold": awarded.delta_gold if awarded else 0,
            "learn_multiplier": float(shower.learn_multiplier),
        }

    async def auto_pick(self, count: int, seed: str) -> list[int]:
        previous = (
            await self.session.execute(self.query().where(MeteorShower.starts_at < utcnow()).order_by(MeteorShower.starts_at.desc()))
        ).scalars().first()
        recent = {link.piece_id for link in previous.pieces} if previous else set()
        stmt = (
            select(Piece.id)
            .where(
                Piece.is_user_created.is_(False),
                Piece.parent_piece_id.is_(None),
                Piece.difficulty_score.is_not(None),
            )
            .order_by(Piece.difficulty_score, Piece.id)
        )
        ids = [piece_id for piece_id in (await self.session.execute(stmt)).scalars().all()]
        fresh = [piece_id for piece_id in ids if piece_id not in recent]
        return spread_pick(fresh if len(fresh) >= count else ids, count, seed)

    async def schedule(
        self,
        *,
        name: str,
        starts_at: Optional[datetime] = None,
        hours: int = DEFAULT_HOURS,
        piece_ids: Optional[Sequence[int]] = None,
        count: int = DEFAULT_COUNT,
        description: Optional[str] = None,
        catch_xp: int = 40,
        catch_gold: int = 25,
        learn_multiplier: float = 1.5,
        created_by: Optional[uuid.UUID] = None,
    ) -> MeteorShower:
        starts_at = starts_at or utcnow()
        if starts_at.tzinfo is None:
            raise ValueError("starts_at needs a timezone")
        if not 1 <= hours <= MAX_HOURS:
            raise ValueError(f"a meteor shower lasts between 1 and {MAX_HOURS} hours")
        ends_at = starts_at + timedelta(hours=hours)
        if await self.overlaps(starts_at, ends_at):
            raise ValueError("another meteor shower already covers part of that window")
        if piece_ids:
            chosen = list(dict.fromkeys(piece_ids))
            found = set(
                (
                    await self.session.execute(
                        select(Piece.id).where(Piece.id.in_(chosen), Piece.is_user_created.is_(False))
                    )
                ).scalars().all()
            )
            missing = [piece_id for piece_id in chosen if piece_id not in found]
            if missing:
                raise ValueError(f"not catalogue pieces: {missing}")
        else:
            chosen = await self.auto_pick(count, seed=starts_at.date().isoformat())
        if not MIN_PIECES <= len(chosen) <= MAX_PIECES:
            raise ValueError(f"a meteor shower has {MIN_PIECES} to {MAX_PIECES} pieces")
        shower = MeteorShower(
            name=name,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            catch_xp=catch_xp,
            catch_gold=catch_gold,
            learn_multiplier=Decimal(str(learn_multiplier)),
            created_by=created_by,
            pieces=[MeteorShowerPiece(piece_id=piece_id, position=index) for index, piece_id in enumerate(chosen)],
        )
        self.session.add(shower)
        await self.session.flush()
        return shower

    async def end(self, shower_id: int, now: Optional[datetime] = None) -> Optional[MeteorShower]:
        now = now or utcnow()
        shower = await self.session.get(MeteorShower, shower_id)
        if shower is None:
            return None
        if shower.starts_at > now:
            await self.session.execute(delete(MeteorShower).where(MeteorShower.id == shower_id))
            return None
        if shower.ends_at > now:
            shower.ends_at = now
        await self.session.flush()
        return shower

    async def recent(self, limit: int = 20) -> list[MeteorShower]:
        stmt = self.query().order_by(MeteorShower.starts_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())


async def schedule_meteor_shower(hours: int = DEFAULT_HOURS, count: int = DEFAULT_COUNT) -> Optional[int]:
    from app.core.database import session_scope

    async with session_scope() as session:
        service = MeteorService(session)
        now = utcnow()
        if await service.overlaps(now, now + timedelta(hours=hours)):
            return None
        shower = await service.schedule(
            name=f"Meteor shower, {now.strftime('%d %B').lstrip('0')}",
            description="A handful of catalogue pieces, streaking past for the weekend. Catch one to add it with a bonus.",
            starts_at=now,
            hours=hours,
            count=count,
        )
        return shower.id

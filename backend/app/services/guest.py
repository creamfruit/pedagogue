from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hasher, tokens
from app.models.models import Base, RepertoireEntry, User, Wallet

logger = logging.getLogger("piano.guest")

GUEST_DOMAIN = "guest.pedagogue.app"
SPECIAL_TABLES = {"users", "repertoire_entries", "wallets", "friendships", "subscriptions"}


def guest_email() -> str:
    return f"guest-{uuid.uuid4().hex}@{GUEST_DOMAIN}"


async def create_guest(session: AsyncSession) -> User:
    guest = User(email=guest_email(), password_hash=hasher.hash(secrets.token_urlsafe(32)), is_guest=True)
    session.add(guest)
    await session.flush()
    return guest


async def guest_from_token(session: AsyncSession, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    subject = tokens.subject(token.strip())
    if subject is None:
        return None
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        return None
    found = await session.get(User, user_id)
    if found is None or not found.is_guest:
        return None
    return found


def user_references() -> list[tuple[Any, Any]]:
    found = []
    for table in Base.metadata.sorted_tables:
        if table.name in SPECIAL_TABLES:
            continue
        for key in table.foreign_keys:
            if key.column.table.name == "users":
                found.append((table, key.parent))
    return found


def entry_references() -> list[tuple[Any, Any]]:
    found = []
    for table in Base.metadata.sorted_tables:
        for key in table.foreign_keys:
            if key.column.table.name == "repertoire_entries":
                found.append((table, key.parent))
    return found


async def move_rows(session: AsyncSession, table, column, source, target) -> tuple[int, int]:
    try:
        async with session.begin_nested():
            result = await session.execute(update(table).where(column == source).values({column.name: target}))
        return result.rowcount or 0, 0
    except IntegrityError:
        pass
    keys = list(table.primary_key.columns)
    rows = (await session.execute(select(*keys).where(column == source))).all()
    moved = dropped = 0
    for row in rows:
        match = [key == value for key, value in zip(keys, row)]
        try:
            async with session.begin_nested():
                await session.execute(update(table).where(*match).values({column.name: target}))
            moved += 1
        except IntegrityError:
            await session.execute(delete(table).where(*match))
            dropped += 1
    return moved, dropped


def pick_earlier(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return min(first, second)


def pick_later(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


async def merge_entries(session: AsyncSession, guest: User, target: User) -> dict[str, int]:
    guest_rows = (await session.execute(select(RepertoireEntry).where(RepertoireEntry.user_id == guest.id))).scalars().all()
    target_by_piece = {
        entry.piece_id: entry
        for entry in (await session.execute(select(RepertoireEntry).where(RepertoireEntry.user_id == target.id))).scalars().all()
    }
    moved = merged = 0
    for entry in guest_rows:
        keeper = target_by_piece.get(entry.piece_id)
        if keeper is None:
            entry.user_id = target.id
            moved += 1
            continue
        keeper.last_practiced_at = pick_later(keeper.last_practiced_at, entry.last_practiced_at)
        keeper.started_on = pick_earlier(keeper.started_on, entry.started_on)
        keeper.current_tempo_bpm = pick_later(keeper.current_tempo_bpm, entry.current_tempo_bpm)
        keeper.target_tempo_bpm = keeper.target_tempo_bpm or entry.target_tempo_bpm
        keeper.notes = keeper.notes or entry.notes
        keeper.is_verified = keeper.is_verified or entry.is_verified
        await session.flush()
        for table, column in entry_references():
            try:
                async with session.begin_nested():
                    await session.execute(update(table).where(column == entry.id).values({column.name: keeper.id}))
            except IntegrityError:
                continue
        await session.execute(delete(RepertoireEntry).where(RepertoireEntry.id == entry.id))
        merged += 1
    await session.flush()
    return {"entries_moved": moved, "entries_merged": merged}


async def merge_wallet(session: AsyncSession, guest: User, target: User) -> None:
    source = await session.get(Wallet, guest.id)
    if source is None:
        return
    destination = await session.get(Wallet, target.id)
    if destination is None:
        await session.execute(update(Wallet).where(Wallet.user_id == guest.id).values(user_id=target.id))
        return
    destination.xp += source.xp
    destination.gold += source.gold
    destination.lifetime_xp += source.lifetime_xp
    destination.lifetime_gold += source.lifetime_gold
    await session.execute(delete(Wallet).where(Wallet.user_id == guest.id))


def carry_profile(guest: User, target: User) -> None:
    if target.self_level is None:
        target.self_level = guest.self_level
    if target.years_playing is None:
        target.years_playing = guest.years_playing
    if target.hand_span_cm is None:
        target.hand_span_cm = guest.hand_span_cm
    if target.timezone in (None, "", "UTC") and guest.timezone:
        target.timezone = guest.timezone
    if target.tier_quiz_completed_at is None:
        target.tier_quiz_completed_at = guest.tier_quiz_completed_at
    if target.tastes_completed_at is None:
        target.tastes_completed_at = guest.tastes_completed_at


async def merge_guest(session: AsyncSession, guest: User, target: User) -> dict[str, int]:
    if guest.id == target.id or not guest.is_guest or target.is_guest:
        raise ValueError("a guest can only be merged into a different, real account")
    guest_id, target_id = guest.id, target.id
    carry_profile(guest, target)
    await session.flush()
    summary = await merge_entries(session, guest, target)
    await merge_wallet(session, guest, target)
    rows_moved = rows_dropped = 0
    for table, column in user_references():
        moved, dropped = await move_rows(session, table, column, guest_id, target.id)
        rows_moved += moved
        rows_dropped += dropped
    await session.flush()
    await session.execute(delete(User).where(User.id == guest_id))
    session.expire_all()
    await session.refresh(target)
    summary.update(rows_moved=rows_moved, rows_dropped=rows_dropped)
    logger.info("merged guest %s into %s: %s", guest_id, target_id, summary)
    return summary


async def adopt_guest(session: AsyncSession, token: Optional[str], target: User) -> Optional[dict[str, int]]:
    guest = await guest_from_token(session, token)
    if guest is None or guest.id == target.id or target.is_guest:
        return None
    return await merge_guest(session, guest, target)

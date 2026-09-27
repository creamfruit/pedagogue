from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models.models import Friendship, FriendshipStatus, LeaderboardEntry, User
from app.services.onboarding import BaseService

Scope = Literal["friends", "global"]
Keep = Literal["max", "replace"]


def practice_week_board(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"practice-week:{year}-W{week:02d}"


def roulette_board(day: date) -> str:
    return f"roulette:{day.isoformat()}"


def public_name(user: User) -> str:
    return (user.display_name or "").strip() or "Pianist"


def rank_rows(rows: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    previous: Optional[float] = None
    rank = 0
    for position, row in enumerate(sorted(rows, key=lambda r: (-r["score"], r["name"].lower())), start=1):
        if row["score"] != previous:
            rank = position
            previous = row["score"]
        ranked.append({**row, "rank": rank})
    return ranked


class FriendService(BaseService):
    async def friend_ids(self, user: User) -> set[uuid.UUID]:
        rows = await self.session.execute(
            select(Friendship).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
            )
        )
        return {row.addressee_id if row.requester_id == user.id else row.requester_id for row in rows.scalars().all()}

    async def request(self, user: User, email: str) -> None:
        other = (await self.session.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
        if other is None or other.id == user.id:
            return
        existing = (
            await self.session.execute(
                select(Friendship).where(
                    or_(
                        (Friendship.requester_id == user.id) & (Friendship.addressee_id == other.id),
                        (Friendship.requester_id == other.id) & (Friendship.addressee_id == user.id),
                    )
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == FriendshipStatus.PENDING and existing.addressee_id == user.id:
                existing.status = FriendshipStatus.ACCEPTED
                existing.responded_at = datetime.now(timezone.utc)
            return
        self.session.add(Friendship(requester_id=user.id, addressee_id=other.id))
        await self.session.flush()

    async def overview(self, user: User) -> dict:
        rows = (
            await self.session.execute(
                select(Friendship)
                .options(selectinload(Friendship.requester), selectinload(Friendship.addressee))
                .where(or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id))
                .order_by(Friendship.created_at.desc())
            )
        ).scalars().all()
        view = {"friends": [], "incoming": [], "outgoing": []}
        for row in rows:
            other = row.addressee if row.requester_id == user.id else row.requester
            item = {"id": row.id, "user_id": other.id, "name": public_name(other), "since": row.responded_at or row.created_at}
            if row.status == FriendshipStatus.ACCEPTED:
                view["friends"].append(item)
            elif row.status == FriendshipStatus.PENDING:
                view["incoming" if row.addressee_id == user.id else "outgoing"].append(item)
        return view

    async def respond(self, user: User, friendship_id: uuid.UUID, accept: bool) -> None:
        row = await self.session.get(Friendship, friendship_id)
        if row is None or row.addressee_id != user.id or row.status != FriendshipStatus.PENDING:
            raise LookupError("friend request not found")
        if accept:
            row.status = FriendshipStatus.ACCEPTED
            row.responded_at = datetime.now(timezone.utc)
        else:
            await self.session.delete(row)
        await self.session.flush()

    async def remove(self, user: User, friendship_id: uuid.UUID) -> None:
        row = await self.session.get(Friendship, friendship_id)
        if row is None or user.id not in (row.requester_id, row.addressee_id):
            raise LookupError("friendship not found")
        await self.session.delete(row)
        await self.session.flush()


class LeaderboardService(BaseService):
    async def submit(self, board: str, user: User, score: float, detail: Optional[dict] = None, keep: Keep = "max") -> None:
        value = Decimal(str(round(score, 2)))
        stmt = insert(LeaderboardEntry).values(
            board=board, user_id=user.id, score=value, detail=detail or {}, updated_at=datetime.now(timezone.utc)
        )
        if keep == "max":
            stmt = stmt.on_conflict_do_update(
                index_elements=[LeaderboardEntry.board, LeaderboardEntry.user_id],
                set_={"score": value, "detail": stmt.excluded.detail, "updated_at": stmt.excluded.updated_at},
                where=LeaderboardEntry.score < value,
            )
        else:
            stmt = stmt.on_conflict_do_update(
                index_elements=[LeaderboardEntry.board, LeaderboardEntry.user_id],
                set_={"score": value, "detail": stmt.excluded.detail, "updated_at": stmt.excluded.updated_at},
            )
        await self.session.execute(stmt)

    async def clear(self, board: str, user: User) -> None:
        await self.session.execute(delete(LeaderboardEntry).where(LeaderboardEntry.board == board, LeaderboardEntry.user_id == user.id))

    async def standings(self, board: str, viewer: User, scope: Scope = "friends", limit: int = 20) -> dict:
        stmt = select(LeaderboardEntry).options(selectinload(LeaderboardEntry.user)).where(LeaderboardEntry.board == board)
        if scope == "friends":
            members = await FriendService(self.session).friend_ids(viewer) | {viewer.id}
            stmt = stmt.where(LeaderboardEntry.user_id.in_(members))
        entries = (await self.session.execute(stmt)).scalars().all()
        public = rank_rows(
            [
                {"name": public_name(entry.user), "score": float(entry.score), "detail": entry.detail or {}, "is_you": entry.user_id == viewer.id}
                for entry in entries
                if entry.user.leaderboard_opt_in
            ]
        )
        mine = next((entry for entry in entries if entry.user_id == viewer.id), None)
        you = None
        if mine is not None:
            score = float(mine.score)
            listed = next((row for row in public if row["is_you"]), None)
            you = {
                "rank": listed["rank"] if listed else 1 + sum(1 for row in public if row["score"] > score),
                "score": score,
                "detail": mine.detail or {},
                "listed": listed is not None,
            }
        return {
            "board": board,
            "scope": scope,
            "opted_in": viewer.leaderboard_opt_in,
            "rows": public[:limit],
            "you": you,
            "entrants": len(public),
        }

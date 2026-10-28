from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import AdminUser, SessionDep
from app.models.models import Piece

router = APIRouter(prefix="/admin/pieces", tags=["admin"])


class HideRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class HiddenPiece(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    hidden_at: Optional[datetime] = None
    hidden_reason: Optional[str] = None


def forget_caches(piece_id: int) -> None:
    from app.services import keyboard, public_pages, similar

    public_pages.forget_catalogue()
    similar.forget_vectors()
    keyboard.forget(f"piece:{piece_id}")


async def find(session, piece_id: int) -> Piece:
    piece = (await session.execute(select(Piece).where(Piece.id == piece_id))).scalar_one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="piece not found")
    return piece


@router.get("/hidden", response_model=list[HiddenPiece])
async def list_hidden(admin: AdminUser, session: SessionDep) -> list[Piece]:
    rows = await session.execute(select(Piece).where(Piece.hidden_at.is_not(None)).order_by(Piece.hidden_at.desc()))
    return list(rows.scalars().all())


@router.post("/{piece_id}/hide", response_model=HiddenPiece)
async def hide_piece(piece_id: int, payload: HideRequest, admin: AdminUser, session: SessionDep) -> Piece:
    piece = await find(session, piece_id)
    piece.hidden_at = datetime.now(timezone.utc)
    piece.hidden_reason = payload.reason
    piece.hidden_by = admin.id
    await session.commit()
    forget_caches(piece_id)
    return piece


@router.post("/{piece_id}/unhide", response_model=HiddenPiece)
async def unhide_piece(piece_id: int, admin: AdminUser, session: SessionDep) -> Piece:
    piece = await find(session, piece_id)
    piece.hidden_at = None
    piece.hidden_reason = None
    piece.hidden_by = None
    await session.commit()
    forget_caches(piece_id)
    return piece

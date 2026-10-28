from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from app.core.config import settings

SOURCE_NAMES = {
    "mutopia": ("Mutopia Project", "https://www.mutopiaproject.org"),
    "openscore-lieder": ("OpenScore Lieder Corpus", "https://musescore.com/openscore-lieder-corpus"),
}


def report_link(piece_id: int, title: str, source_url: Optional[str] = None, base: Optional[str] = None) -> str:
    base = base or settings.report_problem_url
    subject = f"Problem with {title} (piece {piece_id})"
    lines = ["What is wrong with this piece?", "", "", f"Piece: {title}", f"Pedagogue piece id: {piece_id}"]
    if source_url:
        lines.append(f"Source: {source_url}")
    body = "\n".join(lines)
    if base.startswith("mailto:"):
        return f"{base}?subject={quote(subject)}&body={quote(body)}"
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}title={quote(subject)}&body={quote(body)}"


def harvest_credit(piece) -> Optional[dict]:
    record = getattr(piece, "harvest", None)
    if record is None:
        return None
    name, home = SOURCE_NAMES.get(record.source, (record.source, record.source_url))
    composer = getattr(piece, "composer", None)
    return {
        "source": record.source,
        "source_name": name,
        "source_url": record.source_url or home,
        "licence_code": record.licence_code,
        "licence_name": record.licence_name,
        "licence_url": record.licence_url,
        "composer": record.composer_name,
        "composer_lifespan": composer.lifespan if composer is not None and composer.lifespan else None,
        "attribution": record.attribution,
        "report_url": report_link(piece.id, piece.title, record.source_url),
    }

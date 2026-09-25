from __future__ import annotations

import json
import random
from decimal import Decimal
from typing import Optional, Sequence

from app.core.config import settings
from app.models.models import Technique
from app.services.difficulty import difficulty_band

METADATA_MODEL_HEURISTIC = "heuristic-0.2"
METADATA_MODEL_CLAUDE = "claude-sonnet-4-5"

GRADE_BY_BAND = {
    "unrated": "Unrated",
    "beginner": "RCM 1-3 / ABRSM 1-2",
    "early intermediate": "RCM 4-5 / ABRSM 3-4",
    "intermediate": "RCM 6-7 / ABRSM 5-6",
    "late intermediate": "RCM 8-9 / ABRSM 7-8",
    "advanced": "RCM 10 / ARCT / ABRSM 8+",
    "virtuoso": "Professional / Concert repertoire",
}

PLACEHOLDER_TEXT = {"", "null", "none", "undefined", "n/a", "unknown"}


def clean_text(value: object) -> Optional[str]:
    """Model output is untrusted: keep real prose, turn non-strings and placeholders into None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    collapsed = text.lower().replace("null", "").replace("none", "").replace("undefined", "")
    if text.lower() in PLACEHOLDER_TEXT or not collapsed.strip(" .,-/"):
        return None
    return text


class MetadataGenerator:
    def __init__(self, techniques: Sequence[Technique]) -> None:
        self.techniques = list(techniques)

    async def generate(
        self,
        title: str,
        composer_name: Optional[str],
        genre_name: Optional[str],
        duration_sec: Optional[int],
        difficulty_score: Optional[Decimal],
    ) -> dict:
        if settings.anthropic_api_key:
            try:
                return await self._generate_with_claude(title, composer_name, genre_name, duration_sec, difficulty_score)
            except Exception:
                pass
        return self._generate_heuristic(title, composer_name, genre_name, duration_sec, difficulty_score)

    async def _generate_with_claude(
        self,
        title: str,
        composer_name: Optional[str],
        genre_name: Optional[str],
        duration_sec: Optional[int],
        difficulty_score: Optional[Decimal],
    ) -> dict:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        technique_names = ", ".join(technique.name for technique in self.techniques)
        by_line = f" by {composer_name}" if composer_name else ""
        prompt = (
            f'For the piano piece "{title}"{by_line}, respond with strict JSON only, no prose, matching this '
            'shape: {"techniques": [{"name": "<technique name from the list>", "weight": <float 0 to 1>}], '
            '"hard_bars": [<integer measure numbers>], "historical_note": "<2-3 sentences>", '
            '"fun_fact": "<1-2 sentences>", "syllabus_grade": "<e.g. RCM 8 or ABRSM 6>", '
            '"mood": "<one or two words>", "scene": "<one sentence on what the music evokes>"}. '
            f"Pick 3 to 6 techniques strictly from this list: {technique_names}."
        )
        response = await client.messages.create(
            model=METADATA_MODEL_CLAUDE,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        data = json.loads(text)
        normalized = self._normalize(data)
        normalized["model"] = METADATA_MODEL_CLAUDE
        return normalized

    def _generate_heuristic(
        self,
        title: str,
        composer_name: Optional[str],
        genre_name: Optional[str],
        duration_sec: Optional[int],
        difficulty_score: Optional[Decimal],
    ) -> dict:
        rng = random.Random(f"{title}|{composer_name or ''}")
        pool = self.techniques
        count = min(len(pool), rng.randint(3, 5)) if pool else 0
        chosen = rng.sample(pool, count) if count else []
        techniques = [
            {"technique_id": technique.id, "weight": round(rng.uniform(0.4, 0.95), 2)} for technique in chosen
        ]
        span = max(int((duration_sec or 180) / 4), 10)
        bar_count = min(4, max(span - 4, 1))
        hard_bars = sorted(rng.sample(range(4, span), bar_count)) if span > 4 else [4]
        band = difficulty_band(difficulty_score)
        genre_label = genre_name or "piano"
        historical_note = (
            f'"{title}" sits within the {genre_label} repertoire'
            + (f" of {composer_name}" if composer_name else "")
            + ", and its structure rewards patient, hands-separate study before tempo is built."
        )
        return {
            "techniques": techniques,
            "hard_bars": hard_bars,
            "historical_note": historical_note,
            "fun_fact": "This metadata was generated automatically. Refine it once you know the piece better.",
            "syllabus_grade": GRADE_BY_BAND.get(band, "Unrated"),
            "mood": None,
            "scene": None,
            "model": METADATA_MODEL_HEURISTIC,
        }

    def _normalize(self, data: dict) -> dict:
        by_name = {technique.name.lower(): technique.id for technique in self.techniques}
        techniques = []
        for item in data.get("techniques", []) if isinstance(data.get("techniques"), list) else []:
            technique_id = by_name.get(str(item.get("name", "")).lower())
            if technique_id is None:
                continue
            try:
                weight = max(0.0, min(1.0, float(item.get("weight", 0.6))))
            except (TypeError, ValueError):
                weight = 0.6
            techniques.append({"technique_id": technique_id, "weight": weight})
        hard_bars = [
            int(bar) for bar in (data.get("hard_bars") or []) if isinstance(bar, (int, float)) and not isinstance(bar, bool)
        ]
        return {
            "techniques": techniques,
            "hard_bars": hard_bars,
            "historical_note": clean_text(data.get("historical_note")),
            "fun_fact": clean_text(data.get("fun_fact")),
            "syllabus_grade": clean_text(data.get("syllabus_grade")),
            "mood": clean_text(data.get("mood")),
            "scene": clean_text(data.get("scene")),
        }

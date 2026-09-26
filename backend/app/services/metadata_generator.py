from __future__ import annotations

import random
from decimal import Decimal
from typing import Optional, Sequence

from app.models.models import Technique
from app.services.difficulty import difficulty_band

METADATA_MODEL_HEURISTIC = "heuristic-0.2"

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


METADATA_SYSTEM = (
    "You write catalogue entries for a piano-teaching app used by serious students and teachers. "
    "Accuracy matters more than completeness: an empty field is better than an invented fact, and an "
    "empty bar list is better than guessed bar numbers."
)

TEXT_FIELDS = ("historical_note", "fun_fact", "syllabus_grade", "mood", "scene")


def metadata_schema(technique_names: list[str]) -> dict:
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "techniques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": technique_names},
                        "weight": {"type": "number"},
                    },
                    "required": ["name", "weight"],
                    "additionalProperties": False,
                },
            },
            "hard_bars": {"type": "array", "items": {"type": "integer"}},
            **{field: text for field in TEXT_FIELDS},
        },
        "required": ["techniques", "hard_bars", *TEXT_FIELDS],
        "additionalProperties": False,
    }


class MetadataGenerator:
    def __init__(self, techniques: Sequence[Technique]) -> None:
        self.techniques = list(techniques)

    def prompt(self, title: str, composer_name: Optional[str], genre_name: Optional[str], duration_sec: Optional[int]) -> str:
        details = [f'Piece: "{title}"']
        if composer_name:
            details.append(f"Composer: {composer_name}")
        if genre_name:
            details.append(f"Genre: {genre_name}")
        if duration_sec:
            details.append(f"Typical duration: about {round(duration_sec / 60)} minutes")
        return (
            "\n".join(details)
            + "\n\nFill in the catalogue entry for this solo piano piece.\n"
            "- techniques: the 3 to 6 techniques from the allowed list that carry most of its difficulty, "
            "each with a weight from 0 to 1 for how much of the difficulty it carries.\n"
            "- hard_bars: bar numbers of the hardest passages, only if you are confident of them.\n"
            "- historical_note: 2-3 sentences of context on its composition or reception.\n"
            "- fun_fact: 1-2 sentences a student would enjoy knowing.\n"
            "- syllabus_grade: the usual exam level, e.g. \"RCM 8\" or \"ABRSM 6\", or \"Concert repertoire\".\n"
            "- mood: one or two words for its character.\n"
            "- scene: one sentence on what the music evokes.\n"
            "Leave any text field as an empty string if you are not sure of it."
        )

    async def generate_with_claude(
        self,
        title: str,
        composer_name: Optional[str],
        genre_name: Optional[str],
        duration_sec: Optional[int],
    ):
        from app.services.ai import complete_json

        names = [technique.name for technique in self.techniques]
        completion = await complete_json(
            self.prompt(title, composer_name, genre_name, duration_sec),
            metadata_schema(names),
            system=METADATA_SYSTEM,
            max_tokens=4000,
        )
        normalized = self.normalize(completion.data)
        normalized["model"] = completion.model
        return normalized, completion

    def generate_heuristic(
        self,
        title: str,
        composer_name: Optional[str],
        genre_name: Optional[str],
        duration_sec: Optional[int],
        difficulty_score: Optional[Decimal] = None,
    ) -> dict:
        return self._generate_heuristic(title, composer_name, genre_name, duration_sec, difficulty_score)

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

    def normalize(self, data: dict) -> dict:
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

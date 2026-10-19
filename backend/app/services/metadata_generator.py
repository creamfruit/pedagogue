from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from app.models.models import Technique
from app.services.difficulty import difficulty_band
from app.services.repertoire_reference import (
    LADDER_VERSION,
    Reference,
    estimate_difficulty,
    heuristic_techniques,
)

METADATA_MODEL_HEURISTIC = "heuristic-0.3"
PLACEHOLDER_FACT = "This metadata was generated automatically. Refine it once you know the piece better."

GRADE_BY_BAND = {
    "unrated": "Unrated",
    "beginner": "RCM 1-3 / ABRSM 1-2",
    "early intermediate": "RCM 4-6 / ABRSM 3-5",
    "intermediate": "RCM 7-8 / ABRSM 6-7",
    "late intermediate": "RCM 9-10 / ABRSM 8",
    "advanced": "ARCT / Diploma",
    "virtuoso": "Concert repertoire",
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
            "difficulty": {"type": "number"},
            **{field: text for field in TEXT_FIELDS},
        },
        "required": ["techniques", "hard_bars", "difficulty", *TEXT_FIELDS],
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
            "- difficulty: 1 to 100 on this fixed ladder: Satie Gymnopedie No. 1 = 12, Beethoven Fur Elise = 30, "
            "Debussy Clair de lune = 48, Chopin Fantaisie-Impromptu = 62, Chopin Ballade No. 1 = 70, "
            "Liszt Harmonies du soir = 84, Liszt La Campanella = 90, Balakirev Islamey = 98.\n"
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
        reference: Optional[Reference] = None,
        library: Optional[list[dict]] = None,
    ) -> dict:
        from app.services.score_library import LIBRARY_MODEL, library_difficulty, merged_techniques

        by_name = {technique.name: technique.id for technique in self.techniques}
        if reference:
            links = list(reference.techniques)
        elif library:
            links = merged_techniques(library)
        else:
            links = heuristic_techniques(title, composer_name)
        techniques = [{"technique_id": by_name[name], "weight": weight} for name, weight in links if name in by_name]
        difficulty = reference.score if reference else (library_difficulty(library) if library else None) or estimate_difficulty(title, composer_name)
        return {
            "techniques": techniques,
            "hard_bars": [],
            "difficulty": difficulty,
            "historical_note": reference.history if reference else None,
            "fun_fact": reference.fact if reference else None,
            "syllabus_grade": GRADE_BY_BAND.get(difficulty_band(difficulty), "Unrated"),
            "mood": None,
            "scene": None,
            "model": LADDER_VERSION if reference else (LIBRARY_MODEL if library else METADATA_MODEL_HEURISTIC),
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
        try:
            difficulty = float(data.get("difficulty"))
        except (TypeError, ValueError):
            difficulty = None
        return {
            "techniques": techniques,
            "hard_bars": hard_bars,
            "difficulty": Decimal(str(round(difficulty, 1))) if difficulty and 1 <= difficulty <= 100 else None,
            "historical_note": clean_text(data.get("historical_note")),
            "fun_fact": clean_text(data.get("fun_fact")),
            "syllabus_grade": clean_text(data.get("syllabus_grade")),
            "mood": clean_text(data.get("mood")),
            "scene": clean_text(data.get("scene")),
        }

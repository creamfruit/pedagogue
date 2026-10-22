import re
from typing import Iterable, Optional

FLAT_NAMES = {"b": "-flat", "-": "-flat"}
SHARP_NAMES = {"#": "-sharp"}
OPUS = re.compile(r"^\s*(?:op(?:us)?|o)\b\.?\s*(\d+[a-z]?)(?:\s*[,/]\s*(?:no\.?\s*)?(\d+)|\.?\s*no\.?\s*(\d+))?", re.I)
BARE_NUMBER = re.compile(r"^\s*(\d{1,3}[a-z]?)(?:\s*[,/]\s*(?:no\.?\s*)?(\d+))?\s*$", re.I)
KNOWN_CATALOGUES = re.compile(r"^\s*(BWV|K|KV|D|S|L|M|WoO|Hob|HWV|RV|B|Sz|FP)\b\.?\s*([\w/.-]+)", re.I)
DOTTED_MARKERS = {"K", "KV", "D", "S", "L", "M", "B"}
PIANO_PART_SUFFIX = " (piano part)"
MAX_TITLE = 200


def pretty_key(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    found = re.match(r"^([A-Ga-g])([#b-]?)\s+(major|minor)$", label.strip())
    if not found:
        return None
    note, accidental, mode = found.groups()
    suffix = SHARP_NAMES.get(accidental) or FLAT_NAMES.get(accidental) or ""
    return f"{note.upper()}{suffix} {mode}"


def era_for(eras: Iterable, born: Optional[int]) -> Optional[object]:
    if born is None:
        return None
    active = born + 25
    fitting = [era for era in eras if era.start_year <= active <= (era.end_year or 3000)]
    if not fitting:
        return None
    return min(fitting, key=lambda era: (era.end_year or 3000) - era.start_year)


def catalogue_number(raw: Optional[str]) -> Optional[str]:
    text = (raw or "").strip().rstrip(".")
    if not text:
        return None
    found = OPUS.match(text) or BARE_NUMBER.match(text)
    if found:
        number, sub = found.group(1), found.group(2) or (found.group(3) if found.re is OPUS else None)
        return f"Op. {number}" + (f" No. {sub}" if sub else "")
    known = KNOWN_CATALOGUES.match(text)
    if known:
        marker = {"woo": "WoO", "hob": "Hob."}.get(known.group(1).lower(), known.group(1).upper())
        dotted = "." if marker in DOTTED_MARKERS else ""
        return f"{marker}{dotted} {known.group(2).rstrip('.')}"[:40]
    return text[:40] if len(text) <= 40 and re.search(r"\d", text) else None


def piece_title(title: str, source: str) -> str:
    cleaned = " ".join((title or "").split())
    suffix = PIANO_PART_SUFFIX if source.startswith("openscore") else ""
    return cleaned[: MAX_TITLE - len(suffix)].rstrip() + suffix

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.catalog_match import fold

QUOTES = re.compile(r"[\"“”„«»](?P<text>[^\"“”„«»]{2,80})[\"“”«»]")
KEY = re.compile(
    r"\b(?:in\s+)?(?P<note>[A-Ga-g])(?:\s*[-\s]\s*(?P<acc>flat|sharp)|(?P<sym>[♭♯#b])(?![a-z]))?\s+(?P<mode>major|minor|Major|Minor|dur|moll|Dur|Moll)\b"
)
CATALOGUE = re.compile(
    r"(?P<marker>\bOp(?:us|\.)?|\bS\.|\bBWV|\bKV?\.?|\bHob\.|\bD\.|\bL\.|\bM\.|\bWoO|\bSz\.|\bBB|\bFP|\bTH|\bRV|\bHWV|\bB\.|\bAnh\.)"
    r"\s*(?P<number>(?:[IVX]+\s*[:/]\s*)?\d+[a-z]?(?:/\d+)?)"
    r"(?P<sub>\s*[,:]?\s*(?:No\.?|Nr\.?|n°)\s*\d+[a-z]?)?",
    re.IGNORECASE,
)
ROMAN_LEAD = re.compile(r"(?:^|[:,]\s*)(?P<roman>[IVXL]{1,6})\.\s+(?P<tail>\S.*)$")
LEADING_COUNT = re.compile(r"^\d+\s+(?=\S+s\b)")
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50}
SPACES = re.compile(r"\s{2,}")
EDGE = re.compile(r"^[\s,:;.\-–]+|[\s,:;\-–]+$")
EMPTY_PUNCT = re.compile(r"\s*([,:;])\s*(?=[,:;]|$)")
MODE_NAMES = {"dur": "major", "moll": "minor"}
ACCIDENTALS = {"♭": "flat", "b": "flat", "♯": "sharp", "#": "sharp"}
GERMAN_ACCIDENTAL_NOTES = {"es": "E-flat", "as": "A-flat", "des": "D-flat", "ges": "G-flat", "fis": "F-sharp", "cis": "C-sharp", "gis": "G-sharp", "dis": "D-sharp", "ais": "A-sharp", "b": "B-flat", "h": "B"}
GERMAN_KEY = re.compile(r"\b(?P<note>[A-Ha-h](?:es|is|s)?)-(?P<mode>Dur|dur|Moll|moll)\b")


@dataclass(frozen=True)
class ParsedTitle:
    title: str
    catalog_number: Optional[str]
    key_signature: Optional[str]
    nickname: Optional[str]
    number: Optional[int]


def _key(title: str) -> tuple[Optional[str], Optional[re.Match]]:
    german = GERMAN_KEY.search(title)
    if german:
        raw = german.group("note").lower()
        note = GERMAN_ACCIDENTAL_NOTES.get(raw, raw.upper())
        mode = MODE_NAMES[german.group("mode").lower()]
        return f"{note} {mode}", german
    match = KEY.search(title)
    if not match:
        return None, None
    note = match.group("note").upper()
    accidental = match.group("acc") or ACCIDENTALS.get(match.group("sym") or "")
    mode = match.group("mode").lower()
    mode = MODE_NAMES.get(mode, mode)
    return (f"{note}-{accidental} {mode}" if accidental else f"{note} {mode}"), match


def _catalogue(title: str) -> tuple[Optional[str], Optional[re.Match]]:
    match = CATALOGUE.search(title)
    if not match:
        return None, None
    marker = match.group("marker").strip()
    if marker.lower().startswith("op"):
        marker = "Op."
    elif marker.upper().startswith("K"):
        marker = "K."
    number = match.group("number").replace(" ", "")
    if "/" in number and not re.match(r"^[IVX]", number):
        base, sub = number.split("/", 1)
        text = f"{marker} {base} No. {sub}"
    else:
        text = f"{marker} {number}"
    sub = match.group("sub")
    if sub:
        text += " No. " + re.sub(r"\D", "", sub)
    return text[:40], match


def roman_to_int(text: str) -> int:
    total = 0
    values = [ROMAN_VALUES[ch] for ch in text]
    for index, value in enumerate(values):
        total += -value if index + 1 < len(values) and values[index + 1] > value else value
    return total


def _tidy(text: str) -> str:
    text = re.sub(r"\bin\s*(?=[,:;]|$)", " ", text)
    text = SPACES.sub(" ", text)
    text = re.sub(r"\s+([,:;])", r"\1", text)
    text = re.sub(r"([,:;])(?:\s*[,:;])+", r"\1", text)
    return EDGE.sub("", text).strip()


def parse_work_title(raw: str) -> ParsedTitle:
    title = " ".join((raw or "").split())
    nickname_match = None
    for found in QUOTES.finditer(title):
        nickname_match = found
    nickname = nickname_match.group("text").strip() if nickname_match else None

    catalog_number, catalogue_match = _catalogue(title)
    key_signature, key_match = _key(title)

    number = None
    if catalogue_match:
        sub = catalogue_match.group("sub")
        slash = re.search(r"/(\d+)$", catalogue_match.group("number"))
        if sub:
            number = int(re.sub(r"\D", "", sub))
        elif slash and not re.match(r"^[IVX]", catalogue_match.group("number"), re.IGNORECASE):
            number = int(slash.group(1))

    spans = [m.span() for m in (nickname_match, catalogue_match, key_match) if m is not None]
    stripped = title
    for start, end in sorted(spans, reverse=True):
        stripped = stripped[:start] + " " + stripped[end:]
    stripped = _tidy(stripped)

    movement = None
    roman = ROMAN_LEAD.search(stripped)
    if roman:
        head = _tidy(stripped[: roman.start()])
        tail = roman.group("tail").strip(" .,:")
        value = roman_to_int(roman.group("roman").upper())
        if nickname is None and catalogue_match and not number and head:
            number, nickname, stripped = value, tail, head
            if catalog_number and "No." not in catalog_number:
                catalog_number = f"{catalog_number} No. {value}"[:40]
        else:
            movement = f"{roman.group('roman').upper()}. {tail}"
            stripped = head
            nickname = None

    if not nickname:
        return ParsedTitle(title[:200], catalog_number, key_signature, None, number)
    base = LEADING_COUNT.sub("", stripped)
    base = re.sub(r"[,:]\s*(?=No\.?\s*\d)", " ", base, flags=re.IGNORECASE)
    if number and not re.search(rf"\bNo\.?\s*{number}\b", base, re.IGNORECASE):
        base = f"{base} No. {number}"
    display = base
    if nickname:
        display = f"{base}, {nickname}" if base else nickname
    if movement:
        display = f"{display}: {movement}"
    display = _tidy(display) or title
    return ParsedTitle(display[:200], catalog_number, key_signature, nickname, number)


def match_text(*parts: Optional[str]) -> str:
    text = " ".join(part for part in parts if part)
    text = text.replace("♯", " sharp ").replace("♭", " flat ")
    text = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1 no \2", text)
    text = fold(text)
    text = re.sub(r"\b(?:nr|n°|number)\b", "no", text)
    text = re.sub(r"\bopus\b", "op", text)
    text = re.sub(r"\bkv\b", "k", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return f" {text.strip()} "

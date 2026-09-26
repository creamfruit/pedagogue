from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

CATALOGUE_MARKERS = r"(?:op|opus|s|l|bwv|k|kv|hob|d|woo|cd|sz|bb|fs|m|r|lw|tn|bv)"
CATALOGUE_NUMBER = re.compile(
    r"\b(" + CATALOGUE_MARKERS + r")\.?\s*((?:[ivx]+\s*/?\s*)?\d[\w/.]*)(?:\s*,?\s*no\.?\s*(\d+))?"
)
NON_WORD = re.compile(r"[^a-z0-9]+")
NUMBER_WORD = re.compile(r"\b(?:no|nr|number)\b")
QUOTED = re.compile(r"[\"\u201c\u201d\u201e\u00ab\u00bb][^\"\u201c\u201d\u201e\u00ab\u00bb]*[\"\u201c\u201d\u00ab\u00bb]|\([^)]*\)")
OPUS_ALIASES = {"opus": "op", "kv": "k"}


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _dashes(text: str) -> str:
    return text.replace("‐", "-").replace("–", "-").replace("—", "-")


def catalogue_ids(title: str) -> frozenset[str]:
    ids = set()
    for marker, number, sub in CATALOGUE_NUMBER.findall(_dashes(fold(title))):
        marker = OPUS_ALIASES.get(marker, marker)
        ident = marker + NON_WORD.sub("", number)
        ids.add(ident + (f"n{sub}" if sub else ""))
    return frozenset(ids)


def normalize_title(title: str) -> str:
    folded = CATALOGUE_NUMBER.sub(" ", QUOTED.sub(" ", _dashes(fold(title))))
    folded = NUMBER_WORD.sub(" ", folded)
    return NON_WORD.sub(" ", folded).strip()


def composer_surname(name: Optional[str]) -> str:
    if not name:
        return ""
    if "," in name:
        name = name.split(",", 1)[0]
    tokens = [token for token in NON_WORD.split(fold(name)) if token]
    return tokens[-1] if tokens else ""


def composer_initial(name: Optional[str]) -> str:
    if not name:
        return ""
    if "," in name:
        name = name.split(",", 1)[1]
    tokens = [token for token in NON_WORD.split(fold(name)) if token]
    return tokens[0][0] if tokens else ""


def display_name(name: str, sort_name: Optional[str] = None) -> str:
    if sort_name and not name.isascii() and "," in sort_name:
        last, first = [part.strip() for part in sort_name.split(",", 1)]
        return f"{first} {last}".strip()
    return name


def same_work(title_a: str, composer_a: Optional[str], title_b: str, composer_b: Optional[str]) -> bool:
    if composer_surname(composer_a) != composer_surname(composer_b):
        return False
    ids_a, ids_b = catalogue_ids(title_a), catalogue_ids(title_b)
    if ids_a & ids_b:
        return True
    if normalize_title(title_a) != normalize_title(title_b):
        return False
    return not ids_a or not ids_b


def interleave(groups: tuple[Iterable[dict], ...]) -> list[dict]:
    lists = [list(group) for group in groups]
    ordered: list[dict] = []
    for index in range(max((len(items) for items in lists), default=0)):
        ordered.extend(items[index] for items in lists if index < len(items))
    return ordered


def merge_candidates(*groups: Iterable[dict], limit: int) -> list[dict]:
    merged: list[dict] = []
    for item in interleave(groups):
        match = next(
            (kept for kept in merged if same_work(kept["title"], kept["composer_name"], item["title"], item["composer_name"])),
            None,
        )
        if match is None:
            merged.append({**item, "sources": [item["source"]]})
        elif item["source"] not in match["sources"]:
            match["sources"].append(item["source"])
    return merged[:limit]

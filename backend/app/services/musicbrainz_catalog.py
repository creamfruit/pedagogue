from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.catalog_match import display_name, fold, same_work
from app.services.external_catalog import PIANO_HINTS

logger = logging.getLogger("piano.musicbrainz")

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
APP_VERSION = "0.1.0"
MIN_INTERVAL = 1.1
CACHE_TTL = 15 * 60

EXCLUDED_WORK_TYPES = {
    "song", "song-cycle", "soundtrack", "aria", "opera", "operetta", "musical", "cantata", "mass",
    "motet", "oratorio", "madrigal", "symphony", "symphonic poem", "quartet", "zarzuela", "audio drama",
    "incidental music", "beijing opera", "play", "poem", "prose", "ballet",
}
CHAMBER_PARTNERS = (
    "violin", "violon", "violine", "violino", "viola", "cello", "violoncell", "flute", "flote", "flauto",
    "clarinet", "klarinette", "oboe", "horn", "trumpet", "bassoon", "voice", "voix", "stimme", "soprano",
    "two pianos", "deux pianos", "zwei klaviere", "four hands", "quatre mains", "vierhandig",
)
NON_PIANO_HINTS = (
    "symphon", "quartet", "quatuor", "quartett", "quintet", "trio", "sextet", "octet", "orchestra", "orchestre",
    "orchester", "mass ", "messe", "requiem", "opera", "cantata", "kantate", "overture", "ouverture", "string",
    "streich", "choral", "chorus", "choeur", "lied", "lieder", "song", "chanson", "melodie", "nocturnes, l. 91",
    "nuages", "fetes", "sirenes", "la mer", "faune",
)
ORCHESTRAL_OK_WITH_PIANO = ("concerto", "konzert")
LYRIC_RELATIONS = {"lyricist", "librettist", "writer"}
MOVEMENT = re.compile(r":\s*(?:[ivx]+|\d+)\.\s")
MULTI_MOVEMENT_FORMS = ("concerto", "konzert", "sonata", "sonate", "sonatina", "symphon")


def user_agent() -> str:
    return f"PianoPedagogue/{APP_VERSION} ( {settings.musicbrainz_contact} )"


class Throttle:
    def __init__(self, interval: float = MIN_INTERVAL, clock=time.monotonic, sleep=asyncio.sleep) -> None:
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.lock = asyncio.Lock()
        self.last = float("-inf")

    async def wait(self) -> None:
        async with self.lock:
            delay = self.last + self.interval - self.clock()
            if delay > 0:
                await self.sleep(delay)
            self.last = self.clock()


_throttle = Throttle()
_cache: dict[str, tuple[float, list[dict]]] = {}


def is_classical_composer(artist: dict) -> bool:
    disambiguation = fold(artist.get("disambiguation") or "")
    if "composer" in disambiguation:
        return True
    tags = {fold(tag.get("name", "")) for tag in (artist.get("tags") or []) + (artist.get("genres") or [])}
    return any("classical" in tag or tag in {"baroque", "romantic", "impressionism", "renaissance"} for tag in tags)


def looks_like_piano_work(work: dict) -> bool:
    title = fold(work.get("title") or "")
    if (work.get("type") or "").lower() in EXCLUDED_WORK_TYPES:
        return False
    if work.get("language") not in (None, "zxx"):
        return False
    if MOVEMENT.search(title) and any(form in title for form in MULTI_MOVEMENT_FORMS):
        return False
    if any(relation.get("type") in LYRIC_RELATIONS for relation in work.get("relations") or []):
        return False
    if any(partner in title for partner in CHAMBER_PARTNERS):
        return False
    has_piano = "piano" in title or "klavier" in title or "pianoforte" in title
    if has_piano and any(word in title for word in ORCHESTRAL_OK_WITH_PIANO):
        return True
    if any(hint in title for hint in NON_PIANO_HINTS):
        return False
    return True


def composers_of(work: dict) -> list[dict]:
    return [
        relation["artist"]
        for relation in work.get("relations") or []
        if relation.get("type") == "composer" and relation.get("artist")
    ]


def piano_rank(work: dict) -> int:
    title = fold(work.get("title") or "")
    return 0 if "piano" in title or any(hint in title for hint in PIANO_HINTS) else 1


class MusicBrainzClient:
    def __init__(self, timeout: float = 8.0, transport: Optional[httpx.AsyncBaseTransport] = None, throttle: Optional[Throttle] = None) -> None:
        self.timeout = timeout
        self.transport = transport
        self.throttle = throttle or _throttle

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> Optional[dict]:
        for attempt in range(2):
            await self.throttle.wait()
            try:
                response = await client.get(f"{MUSICBRAINZ_BASE}/{path}", params={**params, "fmt": "json"})
            except httpx.HTTPError:
                logger.warning("musicbrainz %s unreachable", path)
                return None
            if response.status_code == 503 and attempt == 0:
                await asyncio.sleep(2.0)
                continue
            if response.status_code != 200:
                logger.warning("musicbrainz %s returned %s", path, response.status_code)
                return None
            try:
                return response.json()
            except ValueError:
                return None
        return None

    async def search(self, query: str, limit: int = 15) -> list[dict]:
        tokens = [token for token in fold(query).replace('"', " ").split() if token.isalnum() or token.isalpha()]
        if not tokens:
            return []
        cache_key = " ".join(tokens)
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1][:limit]

        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, transport=self.transport) as client:
            composer = await self._find_composer(client, tokens)
            if composer is not None:
                remaining = [token for token in tokens if token not in self._name_tokens(composer)]
                work_query = f"arid:{composer['id']}"
                if remaining:
                    work_query += " AND (" + " OR ".join(f"work:{token}" for token in remaining) + ")"
            else:
                work_query = " AND ".join(f"(work:{token} OR artist:{token})" for token in tokens)
            data = await self._get(client, "work/", {"query": work_query, "limit": 50})

        results = self._normalize(data.get("works", []) if data else [], composer)
        _cache[cache_key] = (time.monotonic(), results)
        return results[:limit]

    async def _find_composer(self, client: httpx.AsyncClient, tokens: list[str]) -> Optional[dict]:
        data = await self._get(
            client, "artist/", {"query": "(" + " OR ".join(tokens) + ") AND type:person", "limit": 5}
        )
        for artist in (data or {}).get("artists", []):
            if int(artist.get("score", 0)) < 85:
                break
            name_tokens = self._name_tokens(artist)
            if any(token in name_tokens for token in tokens) and is_classical_composer(artist):
                return artist
        return None

    @staticmethod
    def _name_tokens(artist: dict) -> set[str]:
        names = [artist.get("name") or "", artist.get("sort-name") or ""]
        names += [alias.get("name") or "" for alias in artist.get("aliases") or []]
        tokens: set[str] = set()
        for name in names:
            tokens.update(fold(name).replace(",", " ").split())
        return tokens

    def _normalize(self, works: list[dict], composer: Optional[dict]) -> list[dict]:
        results: list[dict] = []
        for work in sorted(works, key=lambda w: (piano_rank(w), -int(w.get("score", 0)))):
            if not looks_like_piano_work(work):
                continue
            artists = composers_of(work)
            chosen = next((a for a in artists if composer and a.get("id") == composer.get("id")), None)
            if chosen is None:
                chosen = next((a for a in artists if is_classical_composer(a)), None)
            if chosen is None:
                continue
            name = display_name(chosen.get("name") or "", chosen.get("sort-name"))
            if composer and chosen.get("id") == composer.get("id"):
                name = display_name(composer.get("name") or name, composer.get("sort-name"))
            title = (work.get("title") or "").strip()
            if not title or any(same_work(kept["title"], kept["composer_name"], title, name) for kept in results):
                continue
            life = (composer or {}).get("life-span") if composer and chosen.get("id") == composer.get("id") else None
            results.append(
                {
                    "external_ref": f"musicbrainz:{work['id']}",
                    "title": title,
                    "subtitle": work.get("disambiguation") or None,
                    "composer_name": name,
                    "composer_external_ref": f"musicbrainz:{chosen.get('id')}",
                    "epoch": None,
                    "birth_year": self._year((life or {}).get("begin")),
                    "death_year": self._year((life or {}).get("end")),
                    "source": "musicbrainz",
                }
            )
        return results

    @staticmethod
    def _year(value: Optional[str]) -> Optional[int]:
        if not value or not str(value)[:4].isdigit():
            return None
        return int(str(value)[:4])

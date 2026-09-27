from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from app.services.catalog_match import composer_surname, fold
from app.services.musicbrainz_catalog import MUSICBRAINZ_BASE, Throttle, _throttle, user_agent
from app.services.work_titles import match_text, parse_work_title

logger = logging.getLogger("piano.wiki")

WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
QID = re.compile(r"/(Q\d+)$")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9À-ſ])")
STOP_WORDS = {
    "the", "a", "an", "of", "in", "no", "op", "for", "and", "de", "du", "la", "le", "les", "des", "d", "l", "major",
    "minor", "piano", "sharp", "flat", "s", "bwv", "k", "d", "m", "l", "woo", "hob", "sonata", "etude", "etudes",
    "prelude", "preludes", "suite", "set", "et",
}
MAX_CHARS = 700


@dataclass(frozen=True)
class WikiFact:
    summary: str
    url: str
    title: str
    year: Optional[int] = None


def trim_summary(text: str, limit: int = MAX_CHARS) -> str:
    sentences = SENTENCE.split(" ".join(text.split()))
    kept: list[str] = []
    for sentence in sentences:
        if kept and (len(" ".join(kept)) + len(sentence) > limit or len(kept) >= 4):
            break
        kept.append(sentence)
    return " ".join(kept)[: limit + 200].strip()


def distinctive_tokens(*parts: Optional[str]) -> set[str]:
    return {token for token in match_text(*parts).split() if token not in STOP_WORDS and not token.isdigit() and len(token) > 2}


def plausible_article(article_title: str, snippet: str, work_title: str, composer_name: Optional[str], nickname: Optional[str]) -> bool:
    haystack = match_text(article_title, re.sub(r"<[^>]+>", " ", snippet or ""))
    if nickname and f" {match_text(nickname).strip()} " in haystack:
        return True
    surname = composer_surname(composer_name)
    wanted = distinctive_tokens(work_title)
    if not wanted:
        return False
    found = {token for token in wanted if f" {token} " in haystack}
    if surname and f" {surname} " in haystack:
        return len(found) >= max(1, (len(wanted) + 1) // 2)
    return len(found) == len(wanted) and len(wanted) >= 2


class WikiFactsClient:
    def __init__(self, timeout: float = 8.0, transport: Optional[httpx.AsyncBaseTransport] = None, throttle: Optional[Throttle] = None) -> None:
        self.timeout = timeout
        self.transport = transport
        self.throttle = throttle or _throttle

    async def _json(self, client: httpx.AsyncClient, url: str, params: Optional[dict] = None) -> Optional[dict]:
        try:
            response = await client.get(url, params=params)
        except httpx.HTTPError:
            logger.info("wiki lookup could not reach %s", url.split("?")[0])
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    async def _wikidata_from_musicbrainz(self, client: httpx.AsyncClient, work_id: str) -> tuple[Optional[str], Optional[str]]:
        await self.throttle.wait()
        data = await self._json(client, f"{MUSICBRAINZ_BASE}/work/{work_id}", {"inc": "url-rels", "fmt": "json"})
        qid, wiki_title = None, None
        for relation in (data or {}).get("relations") or []:
            resource = ((relation.get("url") or {}).get("resource")) or ""
            if relation.get("type") == "wikidata":
                found = QID.search(resource)
                qid = found.group(1) if found else qid
            elif relation.get("type") == "wikipedia" and "en.wikipedia.org/wiki/" in resource:
                wiki_title = resource.rsplit("/wiki/", 1)[1]
        return qid, wiki_title

    async def _from_wikidata(self, client: httpx.AsyncClient, qid: str) -> tuple[Optional[str], Optional[int]]:
        data = await self._json(client, WIKIDATA_ENTITY.format(qid=qid))
        entity = ((data or {}).get("entities") or {}).get(qid) or {}
        title = ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")
        year = None
        for claim in (entity.get("claims") or {}).get("P571") or []:
            value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("time")
            if value and re.match(r"^\+\d{4}", value):
                year = int(value[1:5])
                break
        return title, year

    async def _search(self, client: httpx.AsyncClient, work_title: str, composer_name: Optional[str], nickname: Optional[str]) -> Optional[str]:
        surname = composer_surname(composer_name)
        subject = nickname or parse_work_title(work_title).title
        query = f"{surname} {subject}".strip()
        data = await self._json(
            client,
            WIKIPEDIA_API,
            {"action": "query", "list": "search", "srsearch": query, "srlimit": 5, "format": "json", "utf8": 1},
        )
        for hit in ((data or {}).get("query") or {}).get("search") or []:
            if plausible_article(hit.get("title") or "", hit.get("snippet") or "", work_title, composer_name, nickname):
                return hit.get("title")
        return None

    async def _summary(self, client: httpx.AsyncClient, title: str) -> Optional[dict]:
        data = await self._json(client, WIKIPEDIA_SUMMARY.format(title=quote(title.replace(" ", "_"), safe="")))
        if not data or data.get("type") == "disambiguation" or not data.get("extract"):
            return None
        return data

    async def lookup(self, *, title: str, composer_name: Optional[str], external_ref: Optional[str] = None) -> Optional[WikiFact]:
        nickname = parse_work_title(title).nickname
        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, transport=self.transport, follow_redirects=True) as client:
            article, year = None, None
            if external_ref and external_ref.startswith("musicbrainz:"):
                qid, article = await self._wikidata_from_musicbrainz(client, external_ref.split(":", 1)[1])
                if qid:
                    linked, year = await self._from_wikidata(client, qid)
                    article = linked or article
            if not article:
                article = await self._search(client, title, composer_name, nickname)
            if not article:
                return None
            summary = await self._summary(client, article)
            if summary is None:
                return None
            url = ((summary.get("content_urls") or {}).get("desktop") or {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(article.replace(' ', '_'))}"
            return WikiFact(trim_summary(summary["extract"]), url, summary.get("title") or article, year)


def looks_like_same_subject(fact: WikiFact, composer_name: Optional[str]) -> bool:
    surname = composer_surname(composer_name)
    return not surname or surname in fold(fact.summary) or surname in fold(fact.title)

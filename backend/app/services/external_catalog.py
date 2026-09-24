from __future__ import annotations

from typing import Optional

import httpx

OPENOPUS_BASE = "https://api.openopus.org"

PIANO_HINTS = (
    "piano",
    "sonata",
    "etude",
    "study",
    "prelude",
    "nocturne",
    "impromptu",
    "waltz",
    "mazurka",
    "polonaise",
    "ballade",
    "fantaisie",
    "fantasy",
    "variations",
    "fugue",
    "invention",
    "partita",
    "rhapsody",
    "scherzo",
    "toccata",
    "concerto",
)


class OpenOpusClient:
    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, limit: int = 15) -> list[dict]:
        term = query.strip()
        if not term:
            return []
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            composers = await self._search_composers(client, term)
            for composer in composers[:6]:
                for work in await self._works_for_composer(client, composer):
                    key = (work["composer_name"], work["title"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(work)
                    if len(results) >= limit:
                        return results
        return results

    async def _search_composers(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            response = await client.get(f"{OPENOPUS_BASE}/composer/list/search/{term}.json")
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        data = response.json()
        composers = data.get("composers")
        return composers if isinstance(composers, list) else []

    async def _works_for_composer(self, client: httpx.AsyncClient, composer: dict) -> list[dict]:
        composer_id = composer.get("id")
        if not composer_id:
            return []
        works = await self._fetch_works(client, composer_id, "Piano")
        if not works:
            all_works = await self._fetch_works(client, composer_id, "all")
            works = [w for w in all_works if self._looks_like_piano(w.get("title") or "")]
        composer_name = composer.get("complete_name") or composer.get("name") or "Unknown composer"
        normalized = []
        for work in works:
            work_id = work.get("id")
            if not work_id:
                continue
            normalized.append(
                {
                    "external_ref": f"openopus:{composer_id}:{work_id}",
                    "title": (work.get("title") or "Untitled").strip(),
                    "subtitle": work.get("subtitle"),
                    "composer_name": composer_name,
                    "composer_external_ref": f"openopus:{composer_id}",
                    "epoch": composer.get("epoch"),
                    "birth_year": self._year(composer.get("birth")),
                    "death_year": self._year(composer.get("death")),
                }
            )
        return normalized

    async def _fetch_works(self, client: httpx.AsyncClient, composer_id: str, genre: str) -> list[dict]:
        try:
            response = await client.get(f"{OPENOPUS_BASE}/work/list/composer/{composer_id}/genre/{genre}.json")
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        return self._flatten_works(data)

    @staticmethod
    def _flatten_works(data: dict) -> list[dict]:
        if isinstance(data.get("works"), list):
            return data["works"]
        works: list[dict] = []
        for group in data.get("genres") or []:
            group_works = group.get("works")
            if isinstance(group_works, list):
                works.extend(group_works)
        return works

    @staticmethod
    def _looks_like_piano(title: str) -> bool:
        lowered = title.lower()
        return any(hint in lowered for hint in PIANO_HINTS)

    @staticmethod
    def _year(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        digits = "".join(ch for ch in str(value)[:4] if ch.isdigit())
        return int(digits) if digits else None

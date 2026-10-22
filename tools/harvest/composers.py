import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Callable, Optional

from . import config
from .polite import FetchError, PoliteClient

SPARQL = "https://query.wikidata.org/sparql"
ENTITY_API = "https://www.wikidata.org/w/api.php"
COMPOSER_OCCUPATION = "Q36834"
HUMAN = "Q5"

BY_YEARS = """SELECT ?item ?itemLabel (GROUP_CONCAT(DISTINCT ?alt; separator="|") AS ?alts) ?born ?died ?diedPrecision WHERE {{
  ?item wdt:P31 wd:Q5 ; wdt:P106 wd:{occupation} ; wdt:P569 ?born ; wdt:P570 ?died .
  ?item p:P570/psv:P570/wikibase:timePrecision ?diedPrecision .
  FILTER(YEAR(?born) = {born} && YEAR(?died) = {died})
  OPTIONAL {{ ?item skos:altLabel ?alt . FILTER(LANG(?alt) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} GROUP BY ?item ?itemLabel ?born ?died ?diedPrecision"""

TITLES = {"dr", "prof", "sir", "von", "van", "de", "der", "den", "di", "da", "del", "della", "le", "la", "du", "des", "mr", "mrs"}


@dataclass(frozen=True)
class Person:
    qid: str
    label: str
    aliases: tuple
    born: Optional[date]
    died: Optional[date]
    died_precision: int

    def latest_death(self) -> Optional[date]:
        if self.died is None:
            return None
        if self.died_precision >= 11:
            return self.died
        if self.died_precision == 10:
            following = date(self.died.year + (self.died.month == 12), self.died.month % 12 + 1, 1)
            return date.fromordinal(following.toordinal() - 1)
        return date(self.died.year, 12, 31)


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    reason: str
    qid: Optional[str] = None
    label: Optional[str] = None
    died_on: Optional[str] = None

    def to_json(self) -> dict:
        return asdict(self)


def fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", stripped.lower()).strip()


def tokens(name: str) -> list[str]:
    return [part for part in fold(name).split() if part]


def significant(name: str) -> list[str]:
    return [part for part in tokens(name) if len(part) > 1 and part not in TITLES]


def matches_name(name: str, person: Person) -> int:
    wanted = significant(name)
    if not wanted:
        return 0
    surname = wanted[-1]
    best = 0
    for label in (person.label, *person.aliases):
        have = significant(label)
        if not have or surname not in have:
            continue
        score = 1 + sum(1 for part in wanted[:-1] if part in have)
        initials = [part[0] for part in tokens(name)[:-1]]
        if initials and all(any(candidate.startswith(initial) for candidate in have) for initial in initials):
            score += 1
        best = max(best, score)
    return best


def parse_wikidata_date(value: str) -> Optional[date]:
    found = re.match(r"^([+-]?)(\d{1,4})-(\d{2})-(\d{2})", value or "")
    if not found or found.group(1) == "-":
        return None
    year, month, day = int(found.group(2)), max(int(found.group(3)), 1), max(int(found.group(4)), 1)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def years_ago(today: date, years: int) -> date:
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


class ComposerGate:
    def __init__(self, client: PoliteClient, *, today: Optional[date] = None, min_age: int = config.MIN_AGE_YEARS) -> None:
        self.client = client
        self.today = today or date.today()
        self.min_age = min_age
        self._by_years: dict[tuple, list[Person]] = {}
        self._verdicts: dict[tuple, Verdict] = {}

    @property
    def checked(self) -> int:
        return len(self._verdicts)

    def people(self, born: int, died: int) -> list[Person]:
        key = (born, died)
        if key not in self._by_years:
            query = BY_YEARS.format(occupation=COMPOSER_OCCUPATION, born=born, died=died)
            reply = self.client.get(
                SPARQL,
                params={"format": "json", "query": query},
                max_age=config.WIKIDATA_MAX_AGE_SECONDS,
            )
            if not reply.ok:
                raise FetchError(f"Wikidata answered {reply.status} for composers born {born} and died {died}")
            rows = reply.json()["results"]["bindings"]
            self._by_years[key] = [
                Person(
                    qid=row["item"]["value"].rsplit("/", 1)[-1],
                    label=row.get("itemLabel", {}).get("value", ""),
                    aliases=tuple(alias for alias in row.get("alts", {}).get("value", "").split("|") if alias),
                    born=parse_wikidata_date(row["born"]["value"]),
                    died=parse_wikidata_date(row["died"]["value"]),
                    died_precision=int(row["diedPrecision"]["value"]),
                )
                for row in rows
            ]
        return self._by_years[key]

    def entity(self, qid: str) -> Optional[Person]:
        reply = self.client.get(
            ENTITY_API,
            params={"action": "wbgetentities", "ids": qid, "props": "labels|aliases|claims", "languages": "en", "format": "json"},
            max_age=config.WIKIDATA_MAX_AGE_SECONDS,
        )
        if not reply.ok:
            return None
        found = (reply.json().get("entities") or {}).get(qid)
        if not found or "missing" in found:
            return None
        claims = found.get("claims", {})

        def first_time(prop: str):
            for claim in claims.get(prop, []):
                value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value")
                if value and value.get("time"):
                    return parse_wikidata_date(value["time"]), int(value.get("precision", 9))
            return None, 9

        born, _ = first_time("P569")
        died, precision = first_time("P570")
        kinds = {((claim.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}).get("id") for claim in claims.get("P31", [])}
        if HUMAN not in kinds:
            return None
        return Person(
            qid=qid,
            label=(found.get("labels", {}).get("en") or {}).get("value", ""),
            aliases=tuple(item["value"] for item in found.get("aliases", {}).get("en", [])),
            born=born,
            died=died,
            died_precision=precision,
        )

    def judge(self, person: Person, reason_prefix: str = "") -> Verdict:
        latest = person.latest_death()
        if latest is None:
            return Verdict(False, f"{reason_prefix}no death date recorded on Wikidata", person.qid, person.label)
        cutoff = years_ago(self.today, self.min_age)
        if latest < cutoff:
            return Verdict(True, f"died {latest.isoformat()}, more than {self.min_age} years ago", person.qid, person.label, latest.isoformat())
        return Verdict(False, f"{reason_prefix}died {latest.isoformat()}, within the last {self.min_age} years", person.qid, person.label, latest.isoformat())

    def check(self, name: str, born: Optional[int], died: Optional[int], qid: Optional[str] = None) -> Verdict:
        key = (fold(name), born, died, qid)
        if key not in self._verdicts:
            self._verdicts[key] = self.decide(name, born, died, qid)
        return self._verdicts[key]

    def decide(self, name: str, born: Optional[int], died: Optional[int], qid: Optional[str]) -> Verdict:
        if qid:
            person = self.entity(qid)
            if person is None:
                return Verdict(False, f"{qid} is not a person on Wikidata", qid)
            if born and person.born and person.born.year != born or died and person.died and person.died.year != died:
                return Verdict(False, f"{qid} does not match the dates given by the source", qid, person.label)
            return self.judge(person)
        if not name or not born or not died:
            return Verdict(False, "unknown composer: the source gives no name or dates to check against Wikidata")
        ranked = [(matches_name(name, person), person) for person in self.people(born, died)]
        ranked = [(score, person) for score, person in ranked if score > 0]
        if not ranked:
            return Verdict(False, f"unknown composer: no composer called {name} ({born}–{died}) on Wikidata")
        top = max(score for score, _ in ranked)
        best = [person for score, person in ranked if score == top]
        if len({person.qid for person in best}) > 1:
            return Verdict(False, f"ambiguous composer: {name} ({born}–{died}) matches {len(best)} people on Wikidata")
        return self.judge(best[0])

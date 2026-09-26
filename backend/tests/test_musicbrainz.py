import json

import httpx
import pytest

from app.services import musicbrainz_catalog as mb
from app.services.catalog_match import catalogue_ids, merge_candidates, normalize_title, same_work

LISZT = {
    "id": "liszt-id",
    "name": "Franz Liszt",
    "sort-name": "Liszt, Franz",
    "score": 100,
    "disambiguation": "Hungarian composer, pianist and conductor",
    "life-span": {"begin": "1811-10-22", "end": "1886-07-31"},
}
RACH = {"id": "rach-id", "name": "Сергей Рахманинов", "sort-name": "Rachmaninoff, Sergei", "disambiguation": "Russian composer"}
POP = {"id": "pop-id", "name": "Melanie Doane", "sort-name": "Doane, Melanie"}


def composer(artist):
    return {"type": "composer", "direction": "backward", "artist": artist}


WORKS = [
    {"id": "w1", "title": "Mephisto Waltz no. 1, S. 514", "language": "zxx", "score": 100, "relations": [composer(LISZT)]},
    {"id": "w2", "title": "Mephisto Waltz No. 1", "language": "zxx", "score": 98, "relations": [composer(LISZT)]},
    {"id": "w3", "title": "Mephisto Waltz no. 2, S. 515", "language": "zxx", "score": 95, "relations": [composer(LISZT)]},
    {"id": "w4", "title": "Mephisto song", "type": "Song", "language": "eng", "score": 99, "relations": [composer(LISZT)]},
    {"id": "w5", "title": "Mephisto Ballade", "language": "zxx", "score": 97, "relations": [composer(LISZT), {"type": "lyricist", "artist": POP}]},
    {"id": "w6", "title": "Sonate pour violon et piano", "language": "zxx", "score": 96, "relations": [composer(LISZT)]},
    {"id": "w7", "title": "Faust Symphony", "language": "zxx", "score": 94, "relations": [composer(LISZT)]},
    {"id": "w8", "title": "Mephisto groove", "language": "zxx", "score": 93, "relations": [composer(POP)]},
    {"id": "w9", "title": "Piano Concerto no. 1", "language": "zxx", "score": 90, "relations": [composer(LISZT)]},
]


class Recorder:
    def __init__(self, first_status=200):
        self.requests = []
        self.first_status = first_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.first_status != 200 and len(self.requests) == 1:
            return httpx.Response(self.first_status)
        if request.url.path.endswith("/artist/"):
            return httpx.Response(200, json={"artists": [LISZT]})
        return httpx.Response(200, json={"works": WORKS})


class CountingThrottle:
    def __init__(self):
        self.waits = 0

    async def wait(self):
        self.waits += 1


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    monkeypatch.setattr(mb, "_cache", {})
    monkeypatch.setattr(mb.asyncio, "sleep", _no_sleep)


async def _no_sleep(_):
    return None


def test_user_agent_names_app_version_and_contact(monkeypatch):
    monkeypatch.setattr(mb.settings, "musicbrainz_contact", "https://example.org/contact")
    assert mb.user_agent() == "PianoPedagogue/0.1.0 ( https://example.org/contact )"


async def test_throttle_spaces_requests_one_interval_apart():
    now = [0.0]
    slept = []

    async def sleep(seconds):
        slept.append(round(seconds, 3))
        now[0] += seconds

    throttle = mb.Throttle(interval=1.1, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        await throttle.wait()
    assert slept == [1.1, 1.1]


async def test_search_filters_to_classical_piano_works_and_sends_user_agent():
    recorder = Recorder()
    throttle = CountingThrottle()
    client = mb.MusicBrainzClient(transport=httpx.MockTransport(recorder), throttle=throttle)
    results = await client.search("liszt mephisto", 10)
    titles = [r["title"] for r in results]
    assert titles == ["Mephisto Waltz no. 1, S. 514", "Mephisto Waltz no. 2, S. 515", "Piano Concerto no. 1"]
    assert all(r["composer_name"] == "Franz Liszt" and r["source"] == "musicbrainz" for r in results)
    assert results[0]["external_ref"] == "musicbrainz:w1"
    assert (results[0]["birth_year"], results[0]["death_year"]) == (1811, 1886)
    assert throttle.waits == len(recorder.requests) == 2
    assert all(req.headers["user-agent"].startswith("PianoPedagogue/") for req in recorder.requests)
    work_query = recorder.requests[1].url.params["query"]
    assert work_query == "arid:liszt-id AND (work:mephisto)"


async def test_search_is_cached_and_retries_once_on_503():
    recorder = Recorder(first_status=503)
    client = mb.MusicBrainzClient(transport=httpx.MockTransport(recorder), throttle=CountingThrottle())
    first = await client.search("liszt mephisto", 10)
    again = await client.search("Liszt  Mephisto", 10)
    assert first and first == again
    assert len(recorder.requests) == 3


def test_cyrillic_composer_uses_latin_sort_name():
    client = mb.MusicBrainzClient()
    results = client._normalize([{"id": "p", "title": "Prelude in C-sharp minor, op. 3 no. 2", "language": "zxx", "relations": [composer(RACH)]}], None)
    assert results[0]["composer_name"] == "Sergei Rachmaninoff"


def test_same_work_uses_catalogue_numbers_as_evidence():
    assert same_work("Ballade no. 1 in G minor, op. 23", "Fryderyk Chopin", "Ballade No. 1 in G minor", "Frederic Chopin")
    assert not same_work("Sonata in A, D. 959", "Franz Schubert", "Sonata in A, D. 664", "Schubert, Franz")
    assert not same_work("Ballade no. 1", "Chopin", "Ballade no. 2", "Chopin")
    assert catalogue_ids("Prelude, op. 3 no. 2") == frozenset({"op3n2"})
    assert normalize_title("Suite bergamasque, L. 75, CD 82 : III. Clair de lune") == normalize_title("Suite bergamasque : III. Clair de lune")


def test_merge_keeps_first_source_and_records_both():
    openopus = [{"title": "Ballade No. 1 in G minor", "composer_name": "Frédéric Chopin", "source": "openopus"}]
    musicbrainz = [
        {"title": "Ballade no. 1 in G minor, op. 23", "composer_name": "Fryderyk Chopin", "source": "musicbrainz"},
        {"title": "Ballade no. 2 in F major, op. 38", "composer_name": "Fryderyk Chopin", "source": "musicbrainz"},
    ]
    merged = merge_candidates(openopus, musicbrainz, limit=10)
    assert [m["title"] for m in merged] == ["Ballade No. 1 in G minor", "Ballade no. 2 in F major, op. 38"]
    assert merged[0]["sources"] == ["openopus", "musicbrainz"]
    assert merged[1]["sources"] == ["musicbrainz"]


def test_same_work_across_word_order_subtitles_and_movements():
    assert same_work("Sonata for Piano in B minor, S. 178", "Franz Liszt", "Piano Sonata in B minor, S.178", "Franz Liszt")
    assert same_work("Mephisto Waltz no. 1, S. 514 \u201cDer Tanz in der Dorfschenke\u201d", "Franz Liszt", "Mephisto Waltz No. 1", "Franz Liszt")
    assert not mb.looks_like_piano_work({"title": "Concerto for Piano and Orchestra no. 1, S. 124: I. Allegro maestoso", "language": "zxx"})
    assert mb.looks_like_piano_work({"title": "Suite bergamasque : III. Clair de lune", "language": "zxx"})
    assert not mb.looks_like_piano_work({"title": "Sonate pour violon et piano", "language": "zxx"})

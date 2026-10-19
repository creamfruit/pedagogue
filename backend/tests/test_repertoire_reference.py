import json
from types import SimpleNamespace

import httpx
import pytest

from app.seed import MOVEMENT_WORKS, PIECES, TECHNIQUES
from app.services.difficulty import difficulty_band
from app.services.metadata_generator import PLACEHOLDER_FACT, MetadataGenerator
from app.services.piece_knowledge import is_filler
from app.services.repertoire_reference import LADDER, estimate_difficulty, heuristic_techniques, lookup
from app.services.wiki_facts import WikiFactsClient, plausible_article, trim_summary
from app.services.work_titles import parse_work_title

HARMONIES_MB = "Études d'exécution transcendante, S. 139: No. 11 in D-flat major “Harmonies du soir”"


def score(title, composer):
    entry = lookup(title, composer)
    assert entry is not None, title
    return entry.difficulty


def test_ladder_orders_the_famous_cases():
    islamey = score("Islamey, Op. 18", "Mily Balakirev")
    harmonies = score(HARMONIES_MB, "Franz Liszt")
    ballade = score("Ballade no. 1 in G minor, op. 23", "Frédéric Chopin")
    assert islamey >= 97
    assert ballade <= 70
    assert harmonies > ballade
    top = sorted(LADDER, key=lambda entry: -entry.difficulty)[:8]
    assert any(entry.composer == "balakirev" for entry in top)


def test_movement_titles_match_their_own_movement():
    assert score("Piano Sonata no. 14 in C-sharp minor, op. 27 no. 2: III. Presto agitato", "Beethoven") == 68
    assert score("Piano Sonata no. 14 in C-sharp minor, op. 27 no. 2: I. Adagio sostenuto", "Beethoven") == 32
    assert score("Gaspard de la nuit, M. 55: III. Scarbo", "Maurice Ravel") == 98
    assert score("Gaspard de la nuit, M. 55: I. Ondine", "Maurice Ravel") == 88
    assert score("12 Études, op. 10: No. 1 in C major", "Frédéric Chopin") == 90
    assert score("12 Études, op. 10: No. 12 in C minor", "Frédéric Chopin") == 66


def test_composer_must_match():
    assert lookup("Islamey", "Franz Liszt") is None
    assert lookup("Islamey", None) is None


def test_every_seeded_piece_sits_on_the_ladder():
    for title, composer, catalog, _key, _genre, difficulty, _duration, _links in PIECES:
        entry = lookup(title, composer, catalog)
        assert entry is not None, title
        assert round(difficulty * 10, 1) == entry.difficulty, title
    for title, composer, catalog, _key, _genre, difficulty, movements in MOVEMENT_WORKS:
        assert lookup(title, composer, catalog).difficulty == round(difficulty * 10, 1)
        for name, _number, value, _duration, _links in movements:
            assert lookup(f"{title}, {name}", composer, catalog).difficulty == round(value * 10, 1), name


def test_ladder_uses_real_technique_names():
    names = {name for name, _category, _factor in TECHNIQUES}
    for entry in LADDER:
        assert 0 < entry.difficulty <= 100
        assert entry.techniques
        for name, weight in entry.techniques:
            assert name in names, (entry.alternatives, name)
            assert 0 < weight <= 1


def test_parse_musicbrainz_title():
    parsed = parse_work_title(HARMONIES_MB)
    assert parsed.catalog_number == "S. 139 No. 11"
    assert parsed.key_signature == "D-flat major"
    assert parsed.nickname == "Harmonies du soir"
    assert parsed.title.endswith("No. 11, Harmonies du soir")
    roman = parse_work_title("Études d'exécution transcendante, S. 139: XI. Harmonies du soir")
    assert roman.number == 11 and roman.catalog_number == "S. 139 No. 11"
    plain = parse_work_title("Nocturne in E-flat major, Op. 9 No. 2")
    assert plain.title == "Nocturne in E-flat major, Op. 9 No. 2"
    assert plain.catalog_number == "Op. 9 No. 2"
    assert parse_work_title("Sonate h-Moll, S. 178").key_signature == "B minor"


def test_estimate_stays_below_the_reference_summit():
    assert estimate_difficulty("Sonatina in G major", "Ludwig van Beethoven") < estimate_difficulty("Piano Sonata in F minor", "Ludwig van Beethoven")
    assert estimate_difficulty("Grande étude de concert", "Franz Liszt") <= 94
    assert heuristic_techniques("Nocturne in B major", "Frédéric Chopin")[0][0] == "Melody over accompaniment"


def test_offline_generator_invents_nothing():
    techniques = [SimpleNamespace(id=index, name=name) for index, (name, _c, _f) in enumerate(TECHNIQUES, start=1)]
    generator = MetadataGenerator(techniques)
    unknown = generator.generate_heuristic("Valse in A minor, B. 150", "Frédéric Chopin", None, 150)
    assert unknown["hard_bars"] == []
    assert unknown["fun_fact"] is None and unknown["historical_note"] is None
    assert unknown == generator.generate_heuristic("Valse in A minor, B. 150", "Frédéric Chopin", None, 150)
    reference = lookup("Islamey, Op. 18", "Mily Balakirev")
    known = generator.generate_heuristic("Islamey, Op. 18", "Mily Balakirev", None, 480, reference=reference)
    assert float(known["difficulty"]) == 98
    assert known["syllabus_grade"] == "Concert repertoire"
    assert "Caucasus" in known["historical_note"]
    assert difficulty_band(known["difficulty"]) == "virtuoso"


def test_filler_is_recognised():
    assert is_filler(PLACEHOLDER_FACT)
    assert is_filler('"Harmonies" sits within the piano repertoire of Franz Liszt, and its structure rewards patient, hands-separate study before tempo is built.')
    assert not is_filler("Liszt dedicated the set to Czerny.")


def test_trim_summary_keeps_whole_sentences():
    text = "One. " * 3 + "A much longer sentence that goes on. " * 40
    trimmed = trim_summary(text, limit=120)
    assert trimmed.endswith(".")
    assert len(trimmed) <= 320


def test_plausible_article_rejects_unrelated_hits():
    assert plausible_article("Transcendental Études", "set of twelve by Franz <b>Liszt</b> including Harmonies du soir", HARMONIES_MB, "Franz Liszt", "Harmonies du soir")
    assert not plausible_article("Evening (film)", "a 2007 film", "Abendlied", "Robert Schumann", None)


class NoWait:
    async def wait(self):
        return None


async def test_wiki_lookup_follows_musicbrainz_to_wikipedia():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "musicbrainz.org":
            return httpx.Response(200, json={"relations": [{"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q123"}}]})
        if request.url.host == "www.wikidata.org":
            return httpx.Response(200, json={"entities": {"Q123": {
                "sitelinks": {"enwiki": {"title": "Transcendental Études"}},
                "claims": {"P571": [{"mainsnak": {"datavalue": {"value": {"time": "+1852-00-00T00:00:00Z"}}}}]},
            }}})
        if "page/summary" in request.url.path:
            return httpx.Response(200, content=json.dumps({
                "type": "standard",
                "title": "Transcendental Études",
                "extract": "The Transcendental Études are a set of twelve compositions for solo piano by Franz Liszt. They were published in 1852.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Transcendental_%C3%89tudes"}},
            }))
        return httpx.Response(404)

    client = WikiFactsClient(transport=httpx.MockTransport(handler), throttle=NoWait())
    fact = await client.lookup(title=HARMONIES_MB, composer_name="Franz Liszt", external_ref="musicbrainz:abc")
    assert fact is not None
    assert fact.year == 1852
    assert "Liszt" in fact.summary
    assert fact.url.startswith("https://en.wikipedia.org/wiki/")
    assert seen[:2] == ["musicbrainz.org", "www.wikidata.org"]


async def test_wiki_lookup_gives_up_quietly_when_offline():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("blocked")

    client = WikiFactsClient(transport=httpx.MockTransport(handler), throttle=NoWait())
    assert await client.lookup(title="Islamey", composer_name="Mily Balakirev", external_ref="musicbrainz:x") is None

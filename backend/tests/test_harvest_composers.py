from datetime import date

import httpx
import pytest

from tools.harvest.composers import ComposerGate, Person, matches_name, parse_wikidata_date, years_ago
from tools.harvest.licences import parse_licence
from tools.harvest.models import Candidate
from tools.harvest.pipeline import STAGE_COMPOSERS, STAGE_CRAWL, filter_composers
from tools.harvest.polite import FetchError, PoliteClient
from tools.harvest.workspace import Workspace

TODAY = date(2026, 10, 22)


def binding(qid, label, born, died, precision=11, alts=""):
    return {
        "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "itemLabel": {"value": label},
        "alts": {"value": alts},
        "born": {"value": f"{born}T00:00:00Z"},
        "died": {"value": f"{died}T00:00:00Z"},
        "diedPrecision": {"value": str(precision)},
    }


class FakeWikidata:
    def __init__(self, composers=None, entities=None, failing=False):
        self.composers = composers or {}
        self.entities = entities or {}
        self.failing = failing
        self.sparql_calls = 0
        self.entity_calls = 0

    def __call__(self, request):
        if self.failing:
            return httpx.Response(500)
        if request.url.host == "query.wikidata.org":
            self.sparql_calls += 1
            query = request.url.params["query"]
            for (born, died), rows in self.composers.items():
                if f"YEAR(?born) = {born} && YEAR(?died) = {died}" in query:
                    return httpx.Response(200, json={"results": {"bindings": rows}})
            return httpx.Response(200, json={"results": {"bindings": []}})
        self.entity_calls += 1
        qid = request.url.params["ids"]
        return httpx.Response(200, json={"entities": {qid: self.entities.get(qid, {"id": qid, "missing": ""})}})


def gate_for(tmp_path, fake, today=TODAY):
    client = PoliteClient(tmp_path, transport=httpx.MockTransport(fake), sleep=lambda s: None, retries=0)
    return ComposerGate(client, today=today), client


def entity(qid, label, born, died, precision=11, human=True):
    def claim(value):
        return {"mainsnak": {"datavalue": {"value": value}}}

    return {
        "id": qid,
        "labels": {"en": {"value": label}},
        "aliases": {"en": []},
        "claims": {
            "P31": [claim({"id": "Q5" if human else "Q1"})],
            "P569": [claim({"time": f"+{born}T00:00:00Z", "precision": 11})],
            "P570": [claim({"time": f"+{died}T00:00:00Z", "precision": precision})],
        },
    }


CHOPIN = binding("Q1268", "Frédéric Chopin", "1810-03-01", "1849-10-17", alts="Fryderyk Chopin|Chopin")


def test_a_composer_who_died_long_ago_is_accepted(tmp_path):
    gate, _ = gate_for(tmp_path, FakeWikidata({(1810, 1849): [CHOPIN]}))
    verdict = gate.check("F. F. Chopin", 1810, 1849)
    assert verdict.accepted and verdict.qid == "Q1268" and verdict.died_on == "1849-10-17"


def test_a_composer_who_died_within_seventy_years_is_rejected(tmp_path):
    recent = binding("Q2", "Ralph Vaughan Williams", "1872-10-12", "1958-08-26")
    gate, _ = gate_for(tmp_path, FakeWikidata({(1872, 1958): [recent]}))
    verdict = gate.check("R. Vaughan Williams", 1872, 1958)
    assert not verdict.accepted and "within the last 70 years" in verdict.reason


def test_seventy_years_is_measured_to_the_day(tmp_path):
    just_over = binding("Q3", "Old Man", "1880-01-01", "1956-10-21")
    just_under = binding("Q4", "Near Man", "1880-01-01", "1956-10-22")
    gate, _ = gate_for(tmp_path, FakeWikidata({(1880, 1956): [just_over]}))
    assert gate.check("O. Man", 1880, 1956).accepted
    gate, _ = gate_for(tmp_path / "b", FakeWikidata({(1880, 1956): [just_under]}))
    assert not gate.check("N. Man", 1880, 1956).accepted


def test_a_year_only_death_date_counts_from_the_end_of_that_year(tmp_path):
    gate, _ = gate_for(tmp_path, FakeWikidata({(1890, 1956): [binding("Q5", "Year Only", "1890-01-01", "1956-01-01", precision=9)]}))
    assert not gate.check("Y. Only", 1890, 1956).accepted
    gate, _ = gate_for(tmp_path / "b", FakeWikidata({(1890, 1955): [binding("Q6", "Year Only", "1890-01-01", "1955-01-01", precision=9)]}))
    assert gate.check("Y. Only", 1890, 1955).accepted


def test_unknown_composers_are_rejected(tmp_path):
    gate, _ = gate_for(tmp_path, FakeWikidata({(1810, 1849): [CHOPIN]}))
    assert "unknown composer" in gate.check("A. Nobody", 1810, 1849).reason
    assert "unknown composer" in gate.check("Anonymous", None, None).reason
    assert not gate.check("Anonymous", None, None).accepted


def test_a_name_must_match_a_composer_with_the_same_dates(tmp_path):
    gate, _ = gate_for(tmp_path, FakeWikidata({(1810, 1849): [CHOPIN]}))
    assert not gate.check("F. Liszt", 1810, 1849).accepted


def test_two_people_with_the_same_name_and_dates_are_ambiguous(tmp_path):
    twins = [binding("Q10", "Jan Novak", "1700-01-01", "1760-01-01"), binding("Q11", "Jan Novak", "1700-05-05", "1760-02-02")]
    gate, _ = gate_for(tmp_path, FakeWikidata({(1700, 1760): twins}))
    verdict = gate.check("J. Novak", 1700, 1760)
    assert not verdict.accepted and "ambiguous" in verdict.reason


def test_initials_pick_the_right_member_of_a_family(tmp_path):
    family = [
        binding("Q20", "Johann Sebastian Bach", "1685-03-31", "1750-07-28", alts="J. S. Bach"),
        binding("Q21", "Carl Philipp Emanuel Bach", "1685-01-01", "1750-01-01"),
    ]
    gate, _ = gate_for(tmp_path, FakeWikidata({(1685, 1750): family}))
    verdict = gate.check("J. S. Bach", 1685, 1750)
    assert verdict.accepted and verdict.qid == "Q20"


def test_a_source_supplied_identifier_is_verified_against_wikidata(tmp_path):
    fake = FakeWikidata(
        entities={
            "Q7312": entity("Q7312", "Franz Schubert", "1797-01-31", "1828-11-19"),
            "Q99": entity("Q99", "Someone", "1900-01-01", "1990-01-01"),
        }
    )
    gate, _ = gate_for(tmp_path, fake)
    assert gate.check("Franz Schubert", 1797, 1828, "Q7312").accepted
    assert not gate.check("Franz Schubert", 1797, 1829, "Q7312").accepted
    assert "within the last 70 years" in gate.check("Someone", 1900, 1990, "Q99").reason
    assert "not a person" in gate.check("Ghost", None, None, "Q404").reason


def test_an_identifier_that_is_not_a_person_is_rejected(tmp_path):
    fake = FakeWikidata(entities={"Q50": entity("Q50", "A Choir", "1700-01-01", "1760-01-01", human=False)})
    gate, _ = gate_for(tmp_path, fake)
    assert not gate.check("A Choir", 1700, 1760, "Q50").accepted


def test_repeat_checks_and_shared_dates_do_not_repeat_requests(tmp_path):
    fake = FakeWikidata({(1810, 1849): [CHOPIN]})
    gate, _ = gate_for(tmp_path, fake)
    gate.check("F. F. Chopin", 1810, 1849)
    gate.check("F. F. Chopin", 1810, 1849)
    gate.check("F. Liszt", 1810, 1849)
    assert fake.sparql_calls == 1


def test_a_failing_wikidata_stops_the_run_instead_of_accepting_anyone(tmp_path):
    gate, _ = gate_for(tmp_path, FakeWikidata(failing=True))
    with pytest.raises(FetchError):
        gate.check("F. F. Chopin", 1810, 1849)


def test_name_matching_ignores_accents_and_particles():
    person = Person("Q1", "Ludwig van Beethoven", ("L. v. Beethoven",), date(1770, 12, 16), date(1827, 3, 26), 11)
    assert matches_name("L. V. Beethoven", person) > 0
    assert matches_name("Beethovén", person) > 0
    assert matches_name("Bach", person) == 0


def test_wikidata_dates_are_parsed():
    assert parse_wikidata_date("+1849-10-17T00:00:00Z") == date(1849, 10, 17)
    assert parse_wikidata_date("+1849-00-00T00:00:00Z") == date(1849, 1, 1)
    assert parse_wikidata_date("-0100-01-01T00:00:00Z") is None
    assert years_ago(date(2024, 2, 29), 70) == date(1954, 2, 28)


def candidate(source_id, composer, born, died, qid=None):
    return Candidate(
        source="mutopia",
        source_id=source_id,
        title=f"Piece {source_id}",
        composer=composer,
        source_url=f"https://www.mutopiaproject.org/cgibin/piece-info.cgi?id={source_id}",
        licence=parse_licence("Public Domain"),
        licence_text="Public Domain",
        born=born,
        died=died,
        composer_qid=qid,
    )


def test_the_stage_keeps_old_composers_and_records_why_the_rest_were_dropped(tmp_path):
    ws = Workspace(tmp_path / "work")
    ws.write_stage(
        STAGE_CRAWL,
        [candidate("1", "F. F. Chopin", 1810, 1849), candidate("2", "Anonymous", None, None), candidate("3", "R. Vaughan Williams", 1872, 1958)],
        [],
    )
    fake = FakeWikidata({(1810, 1849): [CHOPIN], (1872, 1958): [binding("Q2", "Ralph Vaughan Williams", "1872-10-12", "1958-08-26")]})
    client = PoliteClient(ws.root, transport=httpx.MockTransport(fake), sleep=lambda s: None, retries=0)
    summary = filter_composers(ws, client, STAGE_CRAWL, today=TODAY)
    assert summary["kept"] == 1 and summary["rejected"] == 2
    kept = ws.read_stage(STAGE_COMPOSERS)
    assert kept[0].composer_qid == "Q1268" and kept[0].composer_died_on == "1849-10-17"
    reasons = {row["source_id"]: row["reason"] for row in ws.rejections(STAGE_COMPOSERS)}
    assert "unknown composer" in reasons["2"] and "within the last 70 years" in reasons["3"]

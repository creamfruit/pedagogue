import io
import zipfile

import pytest

from tools.harvest import licences, mutopia, openscore
from tools.harvest.licences import CC0, CC_BY, PUBLIC_DOMAIN, is_allowed, parse_licence, rejection_reason

LISTING = """
<table class="outer-table"><tr><td>
<table class="table-bordered result-table">
<tr class="preview"><td colspan="4"><img src="x-preview.png"></td></tr>
<tr><td>Fur Elise</td><td>by L. V. Beethoven (1770&ndash;1827)</td><td>WoO 59</td><td>&nbsp;</td></tr>
<tr><td>for Piano</td><td>1810</td><td>Romantic</td><td></td></tr>
<tr><td>Breitkopf</td><td><a href="../legal.html#publicdomain">Public Domain</a></td><td><a href="piece-info.cgi?id=11">More Information</a></td><td>2001/01/01</td></tr>
<tr><td>Download: <a href="https://m.test/ftp/Fur/fur.ly">.ly file</a></td><td><a href="https://m.test/ftp/Fur/fur.mid">.mid file</a></td><td>x</td><td><a href="https://m.test/ftp/Fur/">FTP</a></td></tr>
</table></td></tr>
<tr><td>
<table class="table-bordered result-table">
<tr><td>Toccatina</td><td>by C.-V. Alkan (1813&ndash;1888)</td><td>Op.75</td><td>&nbsp;</td></tr>
<tr><td>for Piano</td><td></td><td>Romantic</td><td></td></tr>
<tr><td>Edition</td><td><a href="../legal.html#ccasa">Creative Commons Attribution-ShareAlike 4.0</a></td><td><a href="piece-info.cgi?id=12">More Information</a></td><td>2014/01/01</td></tr>
<tr><td>Download: <a href="https://m.test/ftp/T/t.ly">.ly file</a></td><td><a href="https://m.test/ftp/T/t.mid">.mid file</a></td><td>x</td><td>y</td></tr>
</table></td></tr>
<tr><td>
<table class="table-bordered result-table">
<tr><td>Song without Words</td><td>by F. Mendelssohn (1809&ndash;1847)</td><td></td><td></td></tr>
<tr><td>for Voice, Piano</td><td></td><td>Romantic</td><td></td></tr>
<tr><td>Edition</td><td><a href="../legal.html#publicdomain">Public Domain</a></td><td><a href="piece-info.cgi?id=13">More Information</a></td><td>2014/01/01</td></tr>
<tr><td>Download: <a href="https://m.test/ftp/S/s.ly">.ly file</a></td><td><a href="https://m.test/ftp/S/s.mid">.mid file</a></td><td>x</td><td>y</td></tr>
</table></td></tr>
<tr><td>
<table class="table-bordered result-table">
<tr><td>Ballade 4</td><td>by F. F. Chopin (1810&ndash;1849)</td><td>O 52</td><td></td></tr>
<tr><td>for Piano</td><td>1842</td><td>Romantic</td><td></td></tr>
<tr><td>Joseffy</td><td><a href="../legal.html#publicdomain">Public Domain</a></td><td><a href="piece-info.cgi?id=14">More Information</a></td><td>2016/10/28</td></tr>
<tr><td class="zipped">Download: <a href="https://m.test/ftp/C/b4-lys.zip">.ly files (zipped)</a></td><td><a href="https://m.test/ftp/C/b4.mid">.mid file</a></td><td>x</td><td>y</td></tr>
</table></td></tr>
</table>
<a href="make-table.cgi?startat=10&amp;Instrument=Piano">Next 10</a>
"""


@pytest.mark.parametrize(
    "text, code",
    [
        ("Public Domain", PUBLIC_DOMAIN),
        ("public-domain", PUBLIC_DOMAIN),
        ("CC0", CC0),
        ("CC0 1.0 Universal", CC0),
        ("Creative Commons Zero", CC0),
        ("Creative Commons Attribution 4.0", CC_BY),
        ("Creative Commons Attribution 3.0 Unported", CC_BY),
        ("Creative Commons Attribution 2.5", CC_BY),
        ("CC BY 4.0", CC_BY),
        ("cc-by-4.0", CC_BY),
    ],
)
def test_open_licences_are_accepted(text, code):
    found = parse_licence(text)
    assert found is not None and found.code == code
    assert is_allowed(found)


@pytest.mark.parametrize(
    "text",
    [
        "Creative Commons Attribution-ShareAlike 4.0",
        "Creative Commons Attribution-ShareAlike 3.0",
        "CC BY-SA 4.0",
        "cc-by-sa-4.0",
        "Creative Commons Attribution-NonCommercial 4.0",
        "CC BY-NC-SA 4.0",
        "Creative Commons Attribution-NoDerivatives 4.0",
        "Creative Commons Attribution",
        "All rights reserved",
        "Copyright Someone 2015",
        "Free to use",
        "",
        None,
    ],
)
def test_everything_else_is_refused(text):
    assert parse_licence(text) is None


def test_the_refusal_says_why():
    assert "share-alike" in rejection_reason("Creative Commons Attribution-ShareAlike 4.0")
    assert "non-commercial" in rejection_reason("CC BY-NC 4.0")
    assert "none given" in rejection_reason("")
    assert "no clear licence" in rejection_reason("Free to use")


def test_the_listing_parser_reads_every_entry():
    entries, following = mutopia.parse_listing(LISTING)
    assert [entry.mutopia_id for entry in entries] == [11, 12, 13, 14]
    elise = entries[0]
    assert (elise.title, elise.composer, elise.born, elise.died) == ("Fur Elise", "L. V. Beethoven", 1770, 1827)
    assert elise.instrument == "for Piano" and elise.opus == "WoO 59"
    assert elise.ly_url.endswith("fur.ly") and elise.midi_url.endswith("fur.mid")
    assert following == "make-table.cgi?startat=10&Instrument=Piano"


def test_only_solo_piano_works_with_an_open_licence_are_kept():
    entries, _ = mutopia.parse_listing(LISTING)
    outcome = {entry.mutopia_id: mutopia.candidate_from(entry) for entry in entries}
    kept = outcome[11][0]
    assert kept.licence.code == PUBLIC_DOMAIN
    assert kept.source_url == "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=11"
    assert kept.composer == "L. V. Beethoven" and kept.files["ly"].endswith("fur.ly")
    assert outcome[12][1].stage == "licence" and "share-alike" in outcome[12][1].reason
    assert outcome[13][1].stage == "instrument"
    assert outcome[14][0].files["lys"].endswith("b4-lys.zip")


def test_a_composer_line_without_dates_has_no_years():
    assert mutopia.split_composer("by Anonymous") == ("Anonymous", None, None)
    assert mutopia.split_composer("by J. S. Bach (1685–1750)") == ("J. S. Bach", 1685, 1750)
    assert mutopia.split_composer("by Someone (c.1560–1627)") == ("Someone", 1560, 1627)


def test_the_lilypond_header_is_read_and_checked_against_the_catalogue():
    text = '\\version "2.18"\n\\header {\n title = "Fur Elise"\n composer = "Ludwig \\"van\\" Beethoven"\n license = "Public Domain"\n maintainer = "A Typesetter"\n}\n\\score { }'
    header = mutopia.parse_ly_header(text)
    assert header["title"] == "Fur Elise" and header["license"] == "Public Domain" and 'van' in header["composer"]
    entries, _ = mutopia.parse_listing(LISTING)
    candidate = mutopia.candidate_from(entries[0])[0]
    assert mutopia.verify_header(candidate, header) is None
    assert "differs" in mutopia.verify_header(candidate, {"license": "Creative Commons Attribution 4.0"})
    assert "no clear licence" in mutopia.verify_header(candidate, {"title": "x"})


def test_older_files_state_the_licence_as_the_copyright_line():
    entries, _ = mutopia.parse_listing(LISTING)
    candidate = mutopia.candidate_from(entries[0])[0]
    assert mutopia.verify_header(candidate, {"copyright": "Public Domain"}) is None


def test_zipped_sources_are_unpacked_safely(tmp_path):
    archive = tmp_path / "piece-lys.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("piece.ly", '\\header { mutopiacomposer = "X" license = "Public Domain" }\n\\include "part.ily"')
        bundle.writestr("part.ily", "{ c'4 }")
        bundle.writestr("../escape.ly", "bad")
        bundle.writestr("run.exe", "bad")
    written = mutopia.unpack_sources(archive, tmp_path / "out")
    assert sorted(path.name for path in written) == ["part.ily", "piece.ly"]
    assert not (tmp_path / "escape.ly").exists()
    assert mutopia.main_source(written, "piece").name == "piece.ly"


def make_archive(path, members):
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)


def test_openscore_scores_are_listed_with_their_source_licence_and_composer(tmp_path):
    archive = tmp_path / "lieder.zip"
    make_archive(
        archive,
        {
            "Lieder-main/scores/Schubert,_Franz/Winterreise/01_Gute_Nacht/lc123.mscx": "<museScore/>",
            "Lieder-main/scores/Schubert,_Franz/_/Erlkoenig/lc456.mscx": "<museScore/>",
            "Lieder-main/scores/Arne,_Thomas/_/A_Glee/lc789.mscx": "<museScore/>",
            "Lieder-main/README.md": "x",
        },
    )
    scores = {
        123: {"path": "Schubert,_Franz/Winterreise/01_Gute_Nacht", "lyricist": "Mueller", "language": "DE"},
        456: {"path": "Schubert,_Franz/_/Erlkoenig"},
        789: {"path": "Arne,_Thomas/_/A_Glee", "instruments": "Soprano, Alto, Tenor, Bass"},
    }
    composers = {
        1: {"path": "Schubert,_Franz", "name": "Franz Schubert", "born": 1797, "died": 1828, "wikidata": "Q7312"},
        2: {"path": "Arne,_Thomas", "name": "Thomas Arne", "born": 1710, "died": 1778, "wikidata": "Q313344"},
    }
    corpus = openscore.CORPORA[0]
    licence = parse_licence("CC0 1.0 Universal")
    found, rejected = openscore.candidates_from_archive(corpus, licence, archive, scores, composers)
    assert [candidate.source_id for candidate in found] == ["123", "456"]
    first = found[0]
    assert first.title == "Gute Nacht" and first.parent == "Winterreise" and first.extra["number"] == "01"
    assert first.composer == "Franz Schubert" and first.composer_qid == "Q7312" and (first.born, first.died) == (1797, 1828)
    assert first.licence.code == CC0 and first.source_url == "https://musescore.com/score/123"
    assert found[1].parent == ""
    assert len(rejected) == 1 and rejected[0].stage == "instrument"


def test_the_quartet_corpus_is_skipped_because_it_has_no_piano_part():
    quartets = openscore.CORPORA[1]
    assert not quartets.has_piano and "string quartets" in quartets.reason


def test_the_corpus_licence_is_confirmed_from_its_own_licence_file(tmp_path):
    import httpx

    from tools.harvest.polite import PoliteClient

    def handler(request):
        text = "Creative Commons Legal Code\n\nCC0 1.0 Universal\n" if "Lieder" in str(request.url) else "All rights reserved"
        return httpx.Response(200, text=text)

    client = PoliteClient(tmp_path, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert openscore.corpus_licence(client, openscore.CORPORA[0]).code == CC0
    assert openscore.corpus_licence(client, openscore.CORPORA[1]) is None

import io
import uuid
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.services import harvest_library, public_pages, reference_notes, similar
from tests.harvest_helpers import write_study
from tests.test_billing import email_of
from tests.test_keyboard_api import client, needs_db, world  # noqa: F401
from tools.harvest import extract, features as feature_module, scoredata

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><path d='M0 0'/></svg>"


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    path = write_study(tmp_path_factory.mktemp("admin"), "mid")
    data = scoredata.load_score(path, "mid")
    measured = feature_module.extract(data)
    return extract.reference_for(data, measured)


@pytest.fixture
async def harvested(world, study, monkeypatch):
    from sqlalchemy import delete

    from app.models.models import Composer, Passage, PassageSource, Piece, PieceSource, RepertoireEntry

    monkeypatch.setattr(settings, "website_url", "https://pedagogue.test")
    public_pages.forget_catalogue()
    similar.forget_vectors()
    tag = uuid.uuid4().hex[:8]
    async with world.factory() as session:
        composer = Composer(name=f"Harvey Quill {tag}", birth_year=1801, death_year=1870)
        session.add(composer)
        await session.flush()
        piece = Piece(
            title=f"Harvest study {tag}",
            composer_id=composer.id,
            difficulty_score=55,
            technique_vector=[0.3] * 64,
            external_source="mutopia",
            external_ref=f"h{tag}",
            metadata_generation_model="harvest-1",
        )
        near = Piece(title=f"Gentle cousin {tag}", composer_id=composer.id, difficulty_score=30, technique_vector=[0.31] * 64)
        session.add_all([piece, near])
        await session.flush()
        session.add(
            PieceSource(
                piece_id=piece.id,
                source="mutopia",
                source_id=f"h{tag}",
                source_url="https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=999",
                licence_code="cc-by",
                licence_name="CC BY 4.0",
                licence_url="https://creativecommons.org/licenses/by/4.0/",
                composer_name=f"Harvey Quill {tag}",
                composer_died_on=date(1870, 2, 3),
                attribution="Typeset by A Typesetter; Mutopia Project (https://www.mutopiaproject.org)",
                content_hash="a" * 64,
            )
        )
        passage = Passage(piece_id=piece.id, start_measure=5, end_measure=7, label="Octave passage", source=PassageSource.HARVEST, description="Bars 5–7: octaves.", difficulty_score=6.5, image_key=f"harvest/passages/mutopia/h{tag}/5-7.svg")
        session.add(passage)
        entry = RepertoireEntry(user_id=world.ids.user, piece_id=piece.id)
        session.add(entry)
        await session.flush()
        record = await session.get(PieceSource, piece.id)
        await reference_notes.store(session, piece, record, study)
        await session.commit()
        ids = {"piece": piece.id, "near": near.id, "passage": passage.id, "entry": entry.id, "composer": composer.id, "tag": tag}
    world.storage.save(io.BytesIO(SVG), f"harvest/passages/mutopia/h{tag}/5-7.svg")
    try:
        yield ids
    finally:
        async with world.factory() as session:
            await session.execute(delete(RepertoireEntry).where(RepertoireEntry.id == ids["entry"]))
            await session.execute(delete(Piece).where(Piece.id.in_([ids["piece"], ids["near"]])))
            await session.execute(delete(Composer).where(Composer.id == ids["composer"]))
            await session.commit()
        public_pages.forget_catalogue()
        similar.forget_vectors()


async def make_admin(world, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails_raw", await email_of(world, world.ids.user))


def test_the_report_link_names_the_piece_and_its_source():
    link = harvest_library.report_link(42, "Sonatine & more", "https://example.test/piece?id=1", base="https://example.test/issues/new")
    query = parse_qs(urlparse(link).query)
    assert link.startswith("https://example.test/issues/new?")
    assert "Sonatine & more" in query["title"][0] and "piece 42" in query["title"][0]
    assert "Pedagogue piece id: 42" in query["body"][0] and "https://example.test/piece?id=1" in query["body"][0]


def test_the_report_link_can_be_an_email():
    link = harvest_library.report_link(7, "Etude", None, base="mailto:support@example.test")
    assert link.startswith("mailto:support@example.test?subject=")
    assert "body=" in link


def test_a_piece_without_a_harvest_record_has_no_credit():
    from types import SimpleNamespace

    assert harvest_library.harvest_credit(SimpleNamespace(harvest=None)) is None


@needs_db
async def test_the_overview_of_a_harvested_piece_names_its_source_licence_and_report_link(world, harvested):
    async with client() as http:
        body = (await http.get(f"/api/v1/catalog/pieces/{harvested['piece']}/overview")).json()
    source = body["source"]
    assert source["source_name"] == "Mutopia Project" and source["licence_name"] == "CC BY 4.0"
    assert source["licence_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert source["source_url"].startswith("https://www.mutopiaproject.org/")
    assert source["composer"] == f"Harvey Quill {harvested['tag']}" and source["composer_lifespan"] == "1801–1870"
    assert "Typeset by A Typesetter" in source["attribution"]
    assert source["report_url"].startswith(settings.report_problem_url)
    assert f"piece {harvested['piece']}" in source["report_url"].replace("%20", " ")
    assert body["difficulty_basis"] == "harvest"
    section = body["sections"][0]
    assert section["source"] == "harvest" and section["image"] == f"/catalog/passages/{harvested['passage']}/image"


@needs_db
async def test_a_piece_that_was_not_harvested_shows_no_source(world):
    async with client() as http:
        body = (await http.get(f"/api/v1/catalog/pieces/{world.ids.piece}/overview")).json()
    assert body["source"] is None


@needs_db
async def test_the_public_page_of_a_harvested_piece_shows_source_licence_and_report_link(world, harvested):
    slug = public_pages.piece_slug_for(*(await piece_and_composer(world, harvested["piece"])))
    async with client() as http:
        response = await http.get(f"/public/music/{slug}")
    assert response.status_code == 200
    html = response.text
    assert "Where the score for" in html
    assert "Mutopia Project" in html and "CC BY 4.0" in html and "https://creativecommons.org/licenses/by/4.0/" in html
    assert "Report a problem with this piece" in html
    assert "Typeset by A Typesetter" in html
    assert f"/api/v1/catalog/passages/{harvested['passage']}/image" in html
    assert "but easier" in html and f"Gentle cousin {harvested['tag']}" in html


async def piece_and_composer(world, piece_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Piece

    async with world.factory() as session:
        piece = (await session.execute(select(Piece).options(selectinload(Piece.composer)).where(Piece.id == piece_id))).scalar_one()
    return piece, piece.composer


@needs_db
async def test_a_passage_image_is_served_as_svg(world, harvested):
    async with client() as http:
        response = await http.get(f"/api/v1/catalog/passages/{harvested['passage']}/image")
        missing = await http.get("/api/v1/catalog/passages/999999999/image")
    assert response.status_code == 200 and response.headers["content-type"].startswith("image/svg+xml")
    assert response.content == SVG
    assert missing.status_code == 404


@needs_db
async def test_only_admins_can_hide_a_piece(world, harvested, monkeypatch):
    async with client() as http:
        refused = await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/hide", json={"reason": "wrong notes"})
        assert refused.status_code == 403
        await make_admin(world, monkeypatch)
        short = await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/hide", json={"reason": "x"})
        missing = await http.post("/api/v1/admin/pieces/999999999/hide", json={"reason": "wrong notes"})
        assert short.status_code == 422 and missing.status_code == 404
        done = await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/hide", json={"reason": "wrong notes"})
    assert done.status_code == 200
    body = done.json()
    assert body["id"] == harvested["piece"] and body["hidden_reason"] == "wrong notes" and body["hidden_at"]


@needs_db
async def test_a_hidden_piece_vanishes_from_every_surface_at_once(world, harvested, monkeypatch):
    slug = public_pages.piece_slug_for(*(await piece_and_composer(world, harvested["piece"])))
    async with client() as http:
        assert (await http.get(f"/public/music/{slug}")).status_code == 200
        assert (await http.get(f"/api/v1/catalog/pieces/{harvested['piece']}/similar")).status_code == 200
        assert any(item["id"] == harvested["piece"] for item in (await http.get("/api/v1/catalog/pieces", params={"q": f"Harvest study {harvested['tag']}"})).json())
        sibling = (await http.get(f"/api/v1/catalog/pieces/{harvested['near']}/similar", params={"direction": "harder"})).json()
        assert harvested["piece"] in [item["id"] for item in sibling["harder"]]
        await make_admin(world, monkeypatch)
        await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/hide", json={"reason": "licence in doubt"})

        assert (await http.get(f"/public/music/{slug}")).status_code == 404
        assert (await http.get(f"/api/v1/catalog/pieces/{harvested['piece']}")).status_code == 404
        assert (await http.get(f"/api/v1/catalog/pieces/{harvested['piece']}/overview")).status_code == 404
        assert (await http.get(f"/api/v1/catalog/pieces/{harvested['piece']}/similar")).status_code == 404
        assert (await http.get(f"/api/v1/catalog/passages/{harvested['passage']}/image")).status_code == 404
        assert not any(item["id"] == harvested["piece"] for item in (await http.get("/api/v1/catalog/pieces", params={"q": f"Harvest study {harvested['tag']}"})).json())
        sibling = (await http.get(f"/api/v1/catalog/pieces/{harvested['near']}/similar", params={"direction": "harder"})).json()
        assert harvested["piece"] not in [item["id"] for item in sibling["harder"]]
        sitemap = (await http.get("/public/sitemap.xml")).text
        assert slug not in sitemap
        listing = (await http.get("/public/music")).text
        assert f"Harvest study {harvested['tag']}" not in listing
        hidden = (await http.get("/api/v1/admin/pieces/hidden")).json()
        assert [item["id"] for item in hidden if item["id"] == harvested["piece"]] == [harvested["piece"]]


@needs_db
async def test_a_hidden_piece_gives_the_keyboard_no_reference_and_unhiding_restores_everything(world, harvested, monkeypatch):
    await make_admin(world, monkeypatch)
    async with client() as http:
        before = (await http.get(f"/api/v1/keyboard/entries/{harvested['entry']}/reference")).json()
        assert before["available"] is True and before["source"] == "harvest"
        await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/hide", json={"reason": "wrong notes"})
        after = await http.get(f"/api/v1/keyboard/entries/{harvested['entry']}/reference/notes", params={"start_bar": 1, "end_bar": 2})
        assert after.status_code == 409
        restored = await http.post(f"/api/v1/admin/pieces/{harvested['piece']}/unhide")
        assert restored.status_code == 200 and restored.json()["hidden_at"] is None
        again = await http.get(f"/api/v1/keyboard/entries/{harvested['entry']}/reference/notes", params={"start_bar": 1, "end_bar": 2})
        slug = public_pages.piece_slug_for(*(await piece_and_composer(world, harvested["piece"])))
        page = await http.get(f"/public/music/{slug}")
    assert again.status_code == 200 and again.json()["notes"]
    assert page.status_code == 200


@needs_db
async def test_the_keyboard_scores_against_a_ready_harvested_piece_with_no_file_attached(world, harvested):
    async with client() as http:
        summary = (await http.get(f"/api/v1/keyboard/entries/{harvested['entry']}/reference")).json()
        notes = await http.get(f"/api/v1/keyboard/entries/{harvested['entry']}/reference/notes", params={"start_bar": 5, "end_bar": 6})
    assert summary["available"] is True and summary["source"] == "harvest"
    assert summary["first_bar"] == 1 and summary["last_bar"] == 12 and summary["attached"] is None
    assert [item["start_bar"] for item in summary["passages"]] == [5]
    assert notes.status_code == 200
    assert notes.json()["bars"] == [5, 6] and notes.json()["notes"]

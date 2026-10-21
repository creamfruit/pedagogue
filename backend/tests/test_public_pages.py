import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import public_pages
from app.services.public_pages import parse_slug, piece_slug_for, slugify, trimmed

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
SITE = "https://pedagogue.test"


def test_slugs_are_plain_ascii_words():
    assert slugify("Étude in D♯ minor, Op. 8 No. 12") == "etude-in-d-minor-op-8-no-12"
    assert slugify("   ") == ""
    assert len(slugify("a" * 500)) <= public_pages.SLUG_LENGTH


def test_a_slug_starts_with_the_id_so_the_words_can_change():
    composer = SimpleNamespace(name="Frédéric Chopin")
    piece = SimpleNamespace(id=42, title="Nocturne in E-flat major", catalog_number="Op. 9 No. 2")
    assert piece_slug_for(piece, composer) == "42-frederic-chopin-nocturne-in-e-flat-major-op-9-no-2"
    assert parse_slug("42-frederic-chopin-nocturne") == 42
    assert parse_slug("42") == 42


def test_a_catalogue_number_already_in_the_title_is_not_repeated():
    composer = SimpleNamespace(name="Chopin")
    piece = SimpleNamespace(id=7, title="Waltz, Op. 64 No. 2", catalog_number="Op. 64 No. 2")
    assert piece_slug_for(piece, composer) == "7-chopin-waltz-op-64-no-2"


@pytest.mark.parametrize("value", ["", "abc", "-5", "x-12", "12345678901-too-long"])
def test_slugs_without_a_leading_id_are_refused(value):
    assert parse_slug(value) is None


def test_long_text_is_cut_on_a_word():
    assert trimmed("one two three four", 12) == "one two…"
    assert trimmed("short", 50) == "short"
    assert trimmed(None, 10) == ""


@pytest.fixture
async def library(monkeypatch):
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.database import get_session
    from app.models.models import Composer, Passage, PassageSource, Piece, PieceTechnique, Technique, TechniqueCategory

    monkeypatch.setattr(settings, "website_url", SITE)
    public_pages.forget_catalogue()
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:8]
    async with factory() as session:
        composer = Composer(name=f"Quillon {tag}", birth_year=1801, death_year=1870, nationality="Freedonian", bio=f"Quillon wrote for the piano {tag}.", fun_fact="Played with oven gloves.")
        technique = Technique(name=f"Thumb under {tag}", category=TechniqueCategory.DEXTERITY, description="Passing the thumb beneath the hand.", mechanic="Rotate the forearm.", common_fault="Lifting the elbow.")
        session.add_all([composer, technique])
        await session.flush()

        def make(title, **fields):
            return Piece(title=title, composer_id=composer.id, **fields)

        main = make(f"Etude {tag}", catalog_number="Op. 9 No. 1", key_signature="Q major", year_composed=1832, tempo_marking="Vivace", difficulty_score=72, mechanical_load=64, duration_sec=150, historical_note=f"Written for a wedding {tag}.", reference_url="https://en.wikipedia.org/wiki/Etude_test", reference_label="Wikipedia: Etude test", fun_fact="The bride requested it.", metadata_generation_model="score-library-1")
        sibling = make(f"Prelude {tag}", difficulty_score=50, historical_note="Our own short note.", metadata_generation_model="reference-ladder-1")
        private = make(f"Private sketch {tag}", difficulty_score=40, is_user_created=True)
        unrated = make(f"Unrated {tag}")
        session.add_all([main, sibling, private, unrated])
        await session.flush()
        for piece, weight in ((main, 0.9), (sibling, 0.8), (private, 0.8)):
            session.add(PieceTechnique(piece_id=piece.id, technique_id=technique.id, weight=weight))
        session.add_all(
            [
                Passage(piece_id=main.id, start_measure=17, end_measure=24, label="Running thirds", difficulty_score=81, source=PassageSource.CATALOG, description=f"Fast thirds in the right hand {tag}.", practice_cue="Practise in groups of four."),
                Passage(piece_id=main.id, start_measure=1, end_measure=4, label="Opening", difficulty_score=20, source=PassageSource.CATALOG, description="A gentle start."),
                Passage(piece_id=main.id, start_measure=30, end_measure=31, label="Bare", difficulty_score=90, source=PassageSource.CATALOG),
                Passage(piece_id=main.id, start_measure=9, end_measure=12, label="My trouble spot", difficulty_score=99, source=PassageSource.USER, description=f"SECRET user note {tag}."),
                Passage(piece_id=main.id, start_measure=13, end_measure=16, label="From my PDF", difficulty_score=95, source=PassageSource.ANALYZER, description=f"SECRET analysed bars {tag}."),
            ]
        )
        await session.commit()
        ids = SimpleNamespace(composer=composer.id, technique=technique.id, main=main.id, sibling=sibling.id, private=private.id, unrated=unrated.id, tag=tag)
        slugs = SimpleNamespace(
            main=public_pages.piece_slug_for(main, composer),
            sibling=public_pages.piece_slug_for(sibling, composer),
            composer=public_pages.composer_slug(composer),
        )

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield SimpleNamespace(ids=ids, slugs=slugs, factory=factory)
    finally:
        app.dependency_overrides.clear()
        public_pages.forget_catalogue()
        async with factory() as session:
            await session.execute(delete(Piece).where(Piece.id.in_([ids.main, ids.sibling, ids.private, ids.unrated])))
            await session.execute(delete(Technique).where(Technique.id == ids.technique))
            await session.execute(delete(Composer).where(Composer.id == ids.composer))
            await session.commit()
        await engine.dispose()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@needs_db
async def test_a_piece_page_answers_how_hard_it_is(library):
    async with client() as http:
        response = await http.get(f"/public/music/{library.slugs.main}")
    assert response.status_code == 200
    html = response.text
    assert f"<h1>Etude {library.ids.tag}, Op. 9 No. 1</h1>" in html
    assert "How hard is Etude" in html
    assert "72.0" in html and "an advanced piece" in html
    assert "harder than" in html
    assert "Q major" in html and "Vivace" in html and "2 min 30 sec" in html


@needs_db
async def test_the_hardest_sections_come_only_from_the_catalogue_and_never_from_users(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.main}")).text
    assert "Running thirds" in html and f"Fast thirds in the right hand {library.ids.tag}" in html
    assert "Practise in groups of four." in html
    assert html.index("Running thirds") < html.index("Opening")
    assert "SECRET" not in html
    assert "My trouble spot" not in html and "From my PDF" not in html
    assert "Bare" not in html


@needs_db
async def test_the_techniques_are_listed_with_what_goes_wrong(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.main}")).text
    assert f"Thumb under {library.ids.tag}" in html
    assert "Rotate the forearm." in html and "Lifting the elbow." in html


@needs_db
async def test_wikipedia_text_is_credited_linked_and_licensed(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.main}")).text
    assert f"Written for a wedding {library.ids.tag}." in html
    assert 'href="https://en.wikipedia.org/wiki/Etude_test"' in html
    assert "Etude test" in html and "CC BY-SA 4.0" in html and "shortened" in html
    assert "The bride requested it." in html


@needs_db
async def test_our_own_notes_are_not_credited_to_wikipedia(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.sibling}")).text
    assert "Our own short note." in html
    assert "Wikipedia" not in html
    assert "CC BY-SA" not in html


@needs_db
async def test_the_first_edition_credit_appears_only_for_pieces_measured_from_it(library):
    async with client() as http:
        measured = (await http.get(f"/public/music/{library.slugs.main}")).text
        ours = (await http.get(f"/public/music/{library.slugs.sibling}")).text
    assert "Fryderyk Chopin Institute" in measured and "CC BY 4.0" in measured and "the changes are ours" in measured
    assert "Fryderyk Chopin Institute" not in ours


@needs_db
async def test_similar_pieces_are_catalogue_pieces_only(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.main}")).text
    assert f"/music/{library.slugs.sibling}" in html
    assert f"Private sketch {library.ids.tag}" not in html
    assert f"Thumb under {library.ids.tag}" in html


@needs_db
async def test_every_piece_page_invites_people_to_sign_up_on_the_website(library):
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.main}")).text
    assert f'href="{SITE}/register?utm_source=pages&amp;utm_content=piece-{library.ids.main}"' in html
    assert f'href="{SITE}/login"' in html
    assert "Create a free account" in html


@needs_db
async def test_private_and_unrated_pieces_have_no_page(library):
    async with client() as http:
        for piece_id in (library.ids.private, library.ids.unrated, 999999999):
            response = await http.get(f"/public/music/{piece_id}")
            assert response.status_code == 404
            assert 'name="robots" content="noindex"' in response.text
        assert (await http.get("/public/music/not-a-slug")).status_code == 404


@needs_db
async def test_a_stale_or_bare_address_redirects_to_the_canonical_one_on_the_website(library):
    async with client() as http:
        bare = await http.get(f"/public/music/{library.ids.main}", follow_redirects=False)
        old = await http.get(f"/public/music/{library.ids.main}-an-old-name", follow_redirects=False)
        right = await http.get(f"/public/music/{library.slugs.main}", follow_redirects=False)
    assert bare.status_code == old.status_code == 301
    assert bare.headers["location"] == old.headers["location"] == f"{SITE}/music/{library.slugs.main}"
    assert right.status_code == 200


@needs_db
async def test_the_catalogue_listing_shows_catalogue_pieces_grouped_by_composer(library):
    async with client() as http:
        html = (await http.get("/public/music")).text
    assert f"/music/{library.slugs.main}" in html and f"/music/{library.slugs.sibling}" in html
    assert f"/composers/{library.slugs.composer}" in html
    assert f"Private sketch {library.ids.tag}" not in html and f"Unrated {library.ids.tag}" not in html


@needs_db
async def test_a_composer_page_lists_their_pieces_from_easiest_to_hardest(library):
    async with client() as http:
        response = await http.get(f"/public/composers/{library.slugs.composer}")
        html = response.text
        composers = (await http.get("/public/composers")).text
    assert response.status_code == 200
    assert f"Quillon {library.ids.tag}" in html and "Freedonian" in html and "1801" in html
    assert f"Quillon wrote for the piano {library.ids.tag}." in html and "Played with oven gloves." in html
    assert html.index(f"Prelude {library.ids.tag}") < html.index(f"Etude {library.ids.tag}")
    assert f"Private sketch {library.ids.tag}" not in html
    assert f"/composers/{library.slugs.composer}" in composers


@needs_db
async def test_composers_without_public_pieces_have_no_page(library):
    async with client() as http:
        assert (await http.get("/public/composers/999999999")).status_code == 404
        wrong = await http.get(f"/public/composers/{library.ids.composer}-wrong", follow_redirects=False)
    assert wrong.status_code == 301


@needs_db
async def test_pages_are_cacheable_and_errors_are_not(library):
    async with client() as http:
        good = await http.get(f"/public/music/{library.slugs.main}")
        missing = await http.get("/public/music/999999999")
    assert "s-maxage" in good.headers["cache-control"]
    assert missing.headers["cache-control"] == "no-store"


@needs_db
async def test_text_from_the_database_cannot_inject_markup(library):
    from app.models.models import Piece

    async with library.factory() as session:
        piece = await session.get(Piece, library.ids.sibling)
        piece.historical_note = "<script>alert(1)</script> & more"
        await session.commit()
    public_pages.forget_catalogue()
    async with client() as http:
        html = (await http.get(f"/public/music/{library.slugs.sibling}")).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in html


def test_the_website_hands_the_public_pages_to_the_api_before_the_single_page_app():
    from pathlib import Path

    import yaml

    blueprint = yaml.safe_load((Path(__file__).resolve().parents[2] / "render.yaml").read_text(encoding="utf-8"))
    web = next(service for service in blueprint["services"] if service["name"] == "pedagogue-web")
    routes = [(route["source"], route["destination"]) for route in web["routes"]]
    sources = [source for source, _ in routes]
    assert sources[-1] == "/*"
    for path in ("/music", "/music/*", "/composers", "/composers/*"):
        assert path in sources and sources.index(path) < sources.index("/*")
    destinations = dict(routes)
    assert destinations["/music/*"].endswith("/public/music/*")
    assert destinations["/composers"].endswith("/public/composers")


def test_the_public_routes_are_not_part_of_the_documented_api():
    paths = app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/public")]

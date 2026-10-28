import os
import uuid
from types import SimpleNamespace

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import public_pages, similar

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
SITE = "https://pedagogue.test"


def vector(*head):
    return list(head) + [0.0] * (64 - len(head))


@pytest.fixture
async def shelf(monkeypatch):
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.database import get_session
    from app.models.models import Composer, Piece

    monkeypatch.setattr(settings, "website_url", SITE)
    similar.forget_vectors()
    public_pages.forget_catalogue()
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:8]
    async with factory() as session:
        names = ["main", "other", "third"]
        composers = {name: Composer(name=f"{name.title()} Simil {tag}", birth_year=1800, death_year=1870) for name in names}
        session.add_all(composers.values())
        await session.flush()

        def make(title, composer, difficulty, vec, **fields):
            return Piece(title=f"{title} {tag}", composer_id=composers[composer].id, difficulty_score=difficulty, technique_vector=vec, **fields)

        pieces = {
            "target": make("Target", "main", 60, vector(0.5, 0.5, 0.5)),
            "near_easy": make("Near easy", "other", 40, vector(0.5, 0.5, 0.45)),
            "far_easy": make("Far easy", "other", 20, vector(0.1, 0.9, 0.1)),
            "same_level": make("Same level", "third", 58, vector(0.5, 0.5, 0.5)),
            "harder": make("Harder", "third", 80, vector(0.5, 0.5, 0.55)),
            "much_harder": make("Much harder", "third", 95, vector(0.9, 0.1, 0.9)),
            "easy_a": make("Easy a", "main", 30, vector(0.5, 0.5, 0.41)),
            "easy_b": make("Easy b", "main", 31, vector(0.5, 0.5, 0.42)),
            "easy_c": make("Easy c", "main", 32, vector(0.5, 0.5, 0.43)),
            "private": make("Private", "other", 35, vector(0.5, 0.5, 0.5), is_user_created=True),
            "no_vector": make("No vector", "other", 35, None),
            "unrated": make("Unrated", "other", None, vector(0.5, 0.5, 0.5)),
        }
        session.add_all(pieces.values())
        await session.flush()
        child = Piece(title=f"Movement {tag}", composer_id=composers["main"].id, difficulty_score=25, technique_vector=vector(0.5, 0.5, 0.5), parent_piece_id=pieces["target"].id, movement_number=1)
        session.add(child)
        await session.commit()
        ids = SimpleNamespace(**{name: piece.id for name, piece in pieces.items()}, child=child.id, tag=tag)
        slug = public_pages.piece_slug_for(pieces["target"], composers["main"])

    async def override_session():
        async with factory() as inner:
            yield inner

    app.dependency_overrides[get_session] = override_session
    try:
        yield SimpleNamespace(ids=ids, factory=factory, slug=slug)
    finally:
        app.dependency_overrides.clear()
        similar.forget_vectors()
        public_pages.forget_catalogue()
        async with factory() as session:
            await session.execute(delete(Piece).where(Piece.id.in_([value for key, value in vars(ids).items() if key != "tag"])))
            await session.execute(delete(Composer).where(Composer.id.in_([c.id for c in composers.values()])))
            await session.commit()
        await engine.dispose()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@needs_db
async def test_easier_pieces_are_the_nearest_neighbours_that_are_at_least_three_points_easier(shelf):
    async with shelf.factory() as session:
        found = await similar.similar_pieces(session, shelf.ids.target, direction="easier", limit=10)
    easier = found["easier"]
    assert found["basis"] == "vectors"
    assert [item["id"] for item in easier][0] == shelf.ids.near_easy
    assert shelf.ids.same_level not in [item["id"] for item in easier]
    assert shelf.ids.target not in [item["id"] for item in easier]
    assert all(item["difficulty"] <= 57 and item["difference"] <= -3 for item in easier)
    assert [item["similarity"] for item in easier] == sorted((item["similarity"] for item in easier), reverse=True)


@needs_db
async def test_harder_neighbours_are_the_nearest_pieces_at_least_three_points_harder(shelf):
    async with shelf.factory() as session:
        found = await similar.similar_pieces(session, shelf.ids.target, direction="harder", limit=10)
    assert "easier" not in found
    assert [item["id"] for item in found["harder"]] == [shelf.ids.harder, shelf.ids.much_harder]


@needs_db
async def test_both_directions_can_be_asked_for_at_once(shelf):
    async with shelf.factory() as session:
        found = await similar.similar_pieces(session, shelf.ids.target, direction="both", limit=3)
    assert found["easier"] and found["harder"]


@needs_db
async def test_one_composer_cannot_fill_the_list_and_unsuitable_pieces_never_appear(shelf):
    async with shelf.factory() as session:
        found = await similar.similar_pieces(session, shelf.ids.target, direction="easier", limit=12)
    ids = [item["id"] for item in found["easier"]]
    assert sum(1 for item in found["easier"] if item["composer"].startswith("Main")) <= similar.PER_COMPOSER
    for excluded in (shelf.ids.private, shelf.ids.no_vector, shelf.ids.unrated, shelf.ids.child):
        assert excluded not in ids


@needs_db
async def test_a_piece_without_a_vector_falls_back_to_shared_techniques(shelf):
    async with shelf.factory() as session:
        found = await similar.similar_pieces(session, shelf.ids.no_vector, direction="easier")
    assert found["basis"] == "techniques"
    assert isinstance(found["easier"], list)


@needs_db
async def test_an_unknown_piece_and_a_bad_direction_are_refused(shelf):
    async with shelf.factory() as session:
        with pytest.raises(LookupError):
            await similar.similar_pieces(session, 999999999)
        with pytest.raises(ValueError):
            await similar.similar_pieces(session, shelf.ids.target, direction="sideways")


@needs_db
async def test_the_api_returns_easier_neighbours(shelf):
    async with client() as http:
        response = await http.get(f"/api/v1/catalog/pieces/{shelf.ids.target}/similar", params={"direction": "easier", "limit": 2})
        missing = await http.get("/api/v1/catalog/pieces/999999999/similar")
        bad = await http.get(f"/api/v1/catalog/pieces/{shelf.ids.target}/similar", params={"direction": "sideways"})
    assert response.status_code == 200
    body = response.json()
    assert body["piece_id"] == shelf.ids.target and body["basis"] == "vectors"
    assert len(body["easier"]) == 2 and body["harder"] == []
    assert body["easier"][0]["full_title"].startswith("Other Simil")
    assert missing.status_code == 404
    assert bad.status_code == 422


@needs_db
async def test_the_public_piece_page_offers_pieces_like_this_but_easier(shelf):
    async with client() as http:
        response = await http.get(f"/public/music/{shelf.slug}")
    assert response.status_code == 200
    html = response.text
    assert "but easier" in html
    assert f"Near easy {shelf.ids.tag}" in html
    assert "points easier" in html
    assert f"Much harder {shelf.ids.tag}" in html


def test_a_matrix_without_pieces_has_no_neighbours():
    matrix = similar.Matrix(0.0, [], np.zeros((0, 1)), np.zeros(0), {})
    assert matrix.index_of(5) is None

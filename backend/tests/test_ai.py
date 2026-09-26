import asyncio
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.services import ai
from app.services.metadata_generator import MetadataGenerator, metadata_schema

TECHNIQUES = [SimpleNamespace(id=1, name="Double thirds", load_factor=1.7), SimpleNamespace(id=2, name="Trills", load_factor=1.25)]

GOOD_OUTPUT = {
    "techniques": [{"name": "Double thirds", "weight": 0.9}, {"name": "Trills", "weight": 1.4}],
    "hard_bars": [12, 40],
    "historical_note": "Written in 1836.",
    "fun_fact": "",
    "syllabus_grade": "Concert repertoire",
    "mood": "Glittering",
    "scene": "null",
}


class FakeMessages:
    def __init__(self, output=GOOD_OUTPUT, stop_reason="end_turn"):
        self.calls = []
        self.output = output
        self.stop_reason = stop_reason

    async def create(self, **request):
        self.calls.append(request)
        await asyncio.sleep(0.01)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            stop_details=SimpleNamespace(category="cyber") if self.stop_reason == "refusal" else None,
            content=[] if self.stop_reason == "refusal" else [SimpleNamespace(type="text", text=json.dumps(self.output))],
            model="claude-opus-5",
            usage=SimpleNamespace(input_tokens=420, output_tokens=180),
        )


@pytest.fixture
def fake_client(monkeypatch):
    messages = FakeMessages()
    monkeypatch.setattr(ai, "_client", SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    return messages


def walk_objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for value in schema.values():
            yield from walk_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from walk_objects(value)


def test_metadata_schema_is_strict():
    schema = metadata_schema(["Double thirds", "Trills"])
    objects = list(walk_objects(schema))
    assert objects
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert schema["properties"]["techniques"]["items"]["properties"]["name"]["enum"] == ["Double thirds", "Trills"]


async def test_complete_json_uses_structured_output_and_fallbacks(fake_client):
    completion = await ai.complete_json("prompt", {"type": "object"}, system="sys")
    request = fake_client.calls[0]
    assert request["fallbacks"] == "default"
    assert request["betas"] == [ai.FALLBACK_BETA]
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert request["system"] == "sys"
    assert completion.data == GOOD_OUTPUT
    assert (completion.input_tokens, completion.output_tokens) == (420, 180)


async def test_complete_json_raises_on_refusal(monkeypatch):
    messages = FakeMessages(stop_reason="refusal")
    monkeypatch.setattr(ai, "_client", SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    with pytest.raises(ai.GenerationRefused):
        await ai.complete_json("prompt", {"type": "object"})


async def test_generator_normalizes_claude_output(fake_client):
    generated, completion = await MetadataGenerator(TECHNIQUES).generate_with_claude("Etude", "Chopin", "Etude", 120)
    assert generated["techniques"] == [{"technique_id": 1, "weight": 0.9}, {"technique_id": 2, "weight": 1.0}]
    assert generated["hard_bars"] == [12, 40]
    assert generated["fun_fact"] is None
    assert generated["scene"] is None
    assert generated["model"] == "claude-opus-5"
    assert "Chopin" in fake_client.calls[0]["messages"][0]["content"]


TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
async def test_piece_metadata_is_paid_for_once(fake_client, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import AIGeneration, Piece, Technique
    from app.services import piece_metadata

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def scope():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(piece_metadata, "session_scope", scope)
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "test-key")

    async with factory() as session:
        technique = (await session.execute(select(Technique).limit(1))).scalar_one_or_none()
        if technique is None:
            pytest.skip("test database has no techniques; seed it first")
        fake_client.output = {**GOOD_OUTPUT, "techniques": [{"name": technique.name, "weight": 0.8}]}
        piece = Piece(title="Idempotency probe", duration_sec=200)
        session.add(piece)
        await session.commit()
        piece_id = piece.id

    try:
        results = await asyncio.gather(*[piece_metadata.generate_piece_metadata(piece_id) for _ in range(3)])
        again = await piece_metadata.generate_piece_metadata(piece_id)
        assert len(fake_client.calls) == 1
        assert again == "already generated"
        assert results.count("claude-opus-5") == 1
        async with factory() as session:
            stored = await session.get(Piece, piece_id)
            assert stored.metadata_generated_at is not None
            assert stored.difficulty_score is not None
            assert stored.historical_note == "Written in 1836."
    finally:
        async with factory() as session:
            await session.execute(delete(AIGeneration).where(AIGeneration.subject_key == f"piece:{piece_id}"))
            await session.execute(delete(Piece).where(Piece.id == piece_id))
            await session.commit()
        await engine.dispose()

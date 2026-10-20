import io
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_current_user
from app.core.config import settings
from app.main import app
from tests.test_keyboard_api import client, needs_db, world  # noqa: F401


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(settings, "audio_features_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    yield
    app.dependency_overrides.clear()


async def test_audio_uploads_are_still_refused_while_audio_is_coming_soon(signed_in):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            f"/api/v1/repertoire/{uuid.uuid4()}/submissions/audio",
            files={"file": ("take.wav", io.BytesIO(b"RIFF0000WAVE"), "audio/wav")},
        )
    assert response.status_code == 403
    assert "coming soon" in response.json()["detail"].lower()


async def test_a_live_listening_session_cannot_be_started_while_audio_is_coming_soon(signed_in):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/v1/practice/sessions", json={"mode": "live_listening"})
    assert response.status_code == 403
    assert "coming soon" in response.json()["detail"].lower()


def test_the_live_listening_socket_closes_while_audio_is_coming_soon(monkeypatch):
    monkeypatch.setattr(settings, "audio_features_enabled", False)
    with TestClient(app) as http:
        with pytest.raises(WebSocketDisconnect) as closed:
            with http.websocket_connect("/api/v1/practice/live?token=anything"):
                pass
    assert closed.value.code == 4403


def test_keyboard_practice_adds_no_audio_features_to_the_api():
    paths = [path for path in app.openapi()["paths"] if path.startswith("/api/v1/keyboard")]
    assert paths
    assert not any("audio" in path or "record" in path for path in paths)


@needs_db
async def test_keyboard_practice_works_with_the_audio_flag_off(world, monkeypatch):
    monkeypatch.setattr(settings, "audio_features_enabled", False)
    async with client() as http:
        started = await http.post("/api/v1/practice/sessions", json={"mode": "keyboard"})
        assert started.status_code == 201 and started.json()["mode"] == "keyboard"
        attempt = await http.post(
            f"/api/v1/keyboard/entries/{world.ids.bare}/attempts",
            json={"mode": "free", "tempo_bpm": 90, "notes": [{"t": i * 333.0, "midi": 60} for i in range(8)], "duration_sec": 10},
        )
        assert attempt.status_code == 201

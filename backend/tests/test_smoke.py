import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hasher, tokens
from app.main import app


def test_password_round_trip():
    hashed = hasher.hash("piano12345")
    assert hasher.verify("piano12345", hashed)
    assert not hasher.verify("wrongpassword", hashed)


def test_token_round_trip():
    token = tokens.create_access_token("abc-123")
    assert tokens.subject(token) == "abc-123"
    assert tokens.subject("not-a-token") is None


def test_openapi_contains_onboarding_routes():
    paths = app.openapi()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/onboarding/top-ten" in paths
    assert "/api/v1/catalog/pieces" in paths
    assert "/api/v1/repertoire" in paths
    assert "/api/v1/repertoire/{entry_id}/submissions/pdf" in paths
    assert "/api/v1/submissions/{submission_id}/analyses" in paths
    assert "/api/v1/progression/pieces/{piece_id}/prerequisites" in paths
    assert "/api/v1/progression/constellation" in paths
    assert "/api/v1/practice/sessions" in paths
    assert "/api/v1/practice/load" in paths
    assert "/api/v1/drills/forge" in paths
    assert "/api/v1/repertoire/{entry_id}/plans" in paths
    assert "/api/v1/sight-reading" in paths
    assert "/api/v1/polyrhythm/attempts" in paths
    assert "/api/v1/performances" in paths
    assert "/api/v1/performances/{performance_id}/readiness" in paths


def test_websocket_route_registered():
    from starlette.routing import WebSocketRoute

    def collect(router):
        found = []
        for route in getattr(router, "routes", []):
            if isinstance(route, WebSocketRoute):
                found.append(route.path)
            found.extend(collect(getattr(route, "original_router", None) or route))
        return found

    assert any("live" in path for path in collect(app))


@pytest.mark.asyncio
async def test_root():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


@pytest.mark.asyncio
async def test_protected_route_requires_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

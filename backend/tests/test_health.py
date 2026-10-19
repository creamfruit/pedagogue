import asyncio
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.config import settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


async def up():
    return True


async def down():
    raise ConnectionError("connection refused by 10.0.0.5:5432 for user piano")


async def hangs():
    await asyncio.sleep(10)
    return True


@pytest.fixture
def redis_in_use(monkeypatch):
    monkeypatch.setattr(settings, "job_queue", "redis")


async def get_health(monkeypatch, database, redis):
    monkeypatch.setattr(health, "ping_database", database)
    monkeypatch.setattr(health, "ping_redis", redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.get("/health")


async def test_healthy_when_the_database_and_redis_answer(monkeypatch, redis_in_use):
    response = await get_health(monkeypatch, up, up)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True
    assert response.headers["cache-control"] == "no-store"


async def test_unavailable_when_the_database_is_down(monkeypatch, redis_in_use):
    response = await get_health(monkeypatch, down, up)
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["database"]["ok"] is False
    assert "10.0.0.5" not in response.text and "refused" not in response.text


async def test_unavailable_when_redis_is_down_and_in_use(monkeypatch, redis_in_use):
    response = await get_health(monkeypatch, up, down)
    assert response.status_code == 503
    assert response.json()["checks"]["redis"]["ok"] is False


async def test_redis_is_skipped_when_nothing_uses_it(monkeypatch):
    monkeypatch.setattr(settings, "job_queue", "background")
    monkeypatch.setattr(settings, "rate_limit_storage", "memory")
    response = await get_health(monkeypatch, up, down)
    assert response.status_code == 200
    assert response.json()["checks"]["redis"]["ok"] is None


async def test_redis_counts_when_rate_limits_are_stored_there(monkeypatch):
    monkeypatch.setattr(settings, "job_queue", "background")
    monkeypatch.setattr(settings, "rate_limit_storage", "redis")
    response = await get_health(monkeypatch, up, down)
    assert response.status_code == 503


async def test_a_hanging_check_times_out(monkeypatch, redis_in_use):
    monkeypatch.setattr(health, "TIMEOUT_SECONDS", 0.05)
    healthy, report = await health.health_report(database=hangs, redis=up)
    assert not healthy
    assert report["checks"]["database"]["ok"] is False
    assert report["checks"]["database"]["ms"] < 5000


async def test_an_unreachable_redis_is_reported_down(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(health, "TIMEOUT_SECONDS", 1.0)
    result = await health.run_check("redis", health.ping_redis)
    assert result["ok"] is False


def test_the_deploy_waits_on_this_health_check():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    api = next(service for service in blueprint["services"] if service["name"] == "pedagogue-api")
    assert api["healthCheckPath"] == "/health"

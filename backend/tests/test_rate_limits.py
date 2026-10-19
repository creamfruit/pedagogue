import io
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.core.rate_limit import Limit, MemoryBackend, RateLimited, RateLimiter, limiter, validate_limits
from app.core.storage import LocalStorage, QuotaExceeded
from app.main import app
from app.services.repertoire import SubmissionService

PDF = b"%PDF-1.7\n" + b"0" * 64
MUSICXML = b'<?xml version="1.0"?><score-partwise version="4.0"></score-partwise>'


class FakeResult:
    def scalar_one_or_none(self):
        return None


class FakeSession:
    async def execute(self, *args, **kwargs):
        return FakeResult()

    def add(self, item):
        item.id = uuid.uuid4()

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage", "memory")
    limiter.backend = None
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def fake_session():
    yield FakeSession()


@pytest.mark.parametrize(
    ("text", "count", "seconds"),
    [("10/minute", 10, 60), ("5 per hour", 5, 3600), ("100/day", 100, 86400), ("3/15minutes", 3, 900), ("2/seconds", 2, 1)],
)
def test_limits_are_read_from_settings_strings(text, count, seconds):
    assert Limit.parse(text) == Limit(count, seconds)


@pytest.mark.parametrize("text", ["", "ten a minute", "5/fortnight", "/minute"])
def test_bad_limit_strings_are_refused(text):
    with pytest.raises(ValueError):
        Limit.parse(text)


def test_bad_settings_fail_at_startup(monkeypatch):
    validate_limits()
    monkeypatch.setattr(settings, "rate_limit_upload", "lots")
    with pytest.raises(ValueError):
        validate_limits()


async def test_windows_reset_and_identities_are_counted_apart(monkeypatch):
    now = [1000.0]
    backend = MemoryBackend(clock=lambda: now[0])
    rate = RateLimiter(backend)
    monkeypatch.setattr(settings, "rate_limit_upload", "2/minute")
    await rate.check("upload", "alice")
    await rate.check("upload", "alice")
    await rate.check("upload", "bob")
    with pytest.raises(RateLimited) as limited:
        await rate.check("upload", "alice")
    assert 0 < limited.value.retry_after <= 60
    now[0] += 60
    await rate.check("upload", "alice")


async def test_limits_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_upload", "1/hour")
    rate = RateLimiter(MemoryBackend())
    for _ in range(5):
        await rate.check("upload", "alice")


async def test_a_broken_store_falls_back_to_memory(monkeypatch):
    class Broken:
        async def hit(self, key, limit):
            raise ConnectionError("redis down")

    monkeypatch.setattr(settings, "rate_limit_upload", "1/hour")
    rate = RateLimiter(Broken())
    await rate.check("upload", "alice")
    with pytest.raises(RateLimited):
        await rate.check("upload", "alice")


async def test_sign_in_is_limited_per_account(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_sign_in", "3/minute")
    app.dependency_overrides[get_session] = fake_session
    async with client() as http:
        codes = [
            (await http.post("/api/v1/auth/token", json={"email": "Pianist@example.com", "password": "wrong-password"})).status_code
            for _ in range(4)
        ]
        other = await http.post("/api/v1/auth/token", json={"email": "someone@example.com", "password": "wrong-password"})
    assert codes == [401, 401, 401, 429]
    assert other.status_code == 401


async def test_sign_in_is_limited_per_network(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_sign_in_ip", "2/minute")
    app.dependency_overrides[get_session] = fake_session
    async with client() as http:
        responses = [
            await http.post("/api/v1/auth/login", data={"username": f"player{n}@example.com", "password": "wrong-password"})
            for n in range(3)
        ]
    assert [r.status_code for r in responses] == [401, 401, 429]
    assert int(responses[-1].headers["Retry-After"]) > 0


async def test_registration_is_limited_per_network(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_register", "1/hour")
    app.dependency_overrides[get_session] = fake_session
    async with client() as http:
        payload = {"email": "new@example.com", "password": "a-long-password", "display_name": "New"}
        await http.post("/api/v1/auth/register", json=payload)
        limited = await http.post("/api/v1/auth/register", json={**payload, "email": "again@example.com"})
    assert limited.status_code == 429
    assert "Try again later" in limited.json()["detail"]


async def upload(http, body, name):
    return await http.post(f"/api/v1/repertoire/{uuid.uuid4()}/submissions/score", files={"file": (name, io.BytesIO(body))})


def signed_in():
    user = SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = fake_session
    return user


async def refuse(*args, **kwargs):
    raise LookupError("repertoire entry not found")


async def test_uploads_are_limited_per_user(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_upload", "2/hour")
    monkeypatch.setattr(SubmissionService, "add_pdf", refuse)
    signed_in()
    async with client() as http:
        codes = [(await upload(http, MUSICXML, "etude.musicxml")).status_code for _ in range(3)]
    assert codes == [404, 404, 429]


async def test_pdf_analysis_is_limited_separately_from_other_scores(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_pdf_analysis", "1/hour")
    monkeypatch.setattr(SubmissionService, "add_pdf", refuse)
    signed_in()
    async with client() as http:
        first = await upload(http, PDF, "score.pdf")
        second = await upload(http, PDF, "score.pdf")
        digital = await upload(http, MUSICXML, "score.musicxml")
    assert (first.status_code, second.status_code, digital.status_code) == (404, 429, 404)


async def test_a_full_quota_is_reported_as_too_large(monkeypatch):
    async def full(*args, **kwargs):
        raise QuotaExceeded("you have used your 500 MB of upload space")

    monkeypatch.setattr(SubmissionService, "add_pdf", full)
    signed_in()
    async with client() as http:
        response = await upload(http, PDF, "score.pdf")
    assert response.status_code == 413
    assert "upload space" in response.json()["detail"]


def test_uploads_stop_at_the_per_user_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_quota_mb", 1)
    storage = LocalStorage(root=str(tmp_path))
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    chunk = b"x" * (600 * 1024)
    storage.save_for_user(io.BytesIO(chunk), f"scores/{mine}/a.pdf", mine)
    assert storage.user_usage(mine) == len(chunk)
    with pytest.raises(QuotaExceeded):
        storage.save_for_user(io.BytesIO(chunk), f"recordings/{mine}/b.wav", mine)
    assert not storage.exists(f"recordings/{mine}/b.wav")
    storage.save_for_user(io.BytesIO(chunk), f"scores/{theirs}/c.pdf", theirs)
    storage.delete(f"scores/{mine}/a.pdf")
    storage.save_for_user(io.BytesIO(chunk), f"midi/{mine}/d.mid", mine)
    assert storage.user_usage(mine) == len(chunk)

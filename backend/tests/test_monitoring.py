import json

import pytest
import sentry_sdk
from httpx import ASGITransport, AsyncClient
from sentry_sdk.transport import Transport

from app.core.config import settings
from app.core.database import get_session
from app.core.monitoring import init_sentry, scrub, scrub_event
from app.core.rate_limit import limiter
from app.main import app

DSN = "https://public@o0.ingest.sentry.io/0"


class Capture(Transport):
    events: list = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type in ("event", "transaction"):
                Capture.events.append(item.payload.json)


@pytest.fixture
def reporting(monkeypatch):
    Capture.events = []
    monkeypatch.setattr(settings, "sentry_dsn", DSN)
    assert init_sentry("test", transport=Capture)
    yield Capture.events
    sentry_sdk.init(dsn=None)
    app.dependency_overrides.clear()
    limiter.reset()


def test_reporting_is_off_without_a_dsn(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "")
    assert init_sentry("test") is False
    assert not sentry_sdk.get_client().is_active()


def test_scrub_removes_emails_tokens_and_secret_fields():
    cleaned = scrub(
        {
            "message": "no user pianist@example.com",
            "extra": {"password": "hunter22", "api_key": "abc", "note": "Bearer eyJhbGciOi.payload.sig", "bars": [1, 2]},
        }
    )
    assert cleaned["message"] == "no user [email]"
    assert cleaned["extra"]["password"] == "[scrubbed]"
    assert cleaned["extra"]["api_key"] == "[scrubbed]"
    assert "eyJ" not in cleaned["extra"]["note"]
    assert cleaned["extra"]["bars"] == [1, 2]


def test_scrub_event_keeps_only_the_user_id_and_safe_request_fields():
    event = scrub_event(
        {
            "user": {"id": "42", "email": "pianist@example.com", "ip_address": "203.0.113.9", "username": "pianist"},
            "request": {
                "url": "https://api.example.com/login?email=pianist@example.com",
                "query_string": "email=pianist@example.com",
                "method": "POST",
                "headers": {"Authorization": "Bearer abc", "Cookie": "s=1", "X-Forwarded-For": "203.0.113.9", "Accept": "application/json"},
                "cookies": {"s": "1"},
                "data": {"password": "hunter22"},
                "env": {"REMOTE_ADDR": "203.0.113.9"},
            },
            "breadcrumbs": {"values": [{"category": "httplib", "data": {"url": "https://x.test/a?token=1"}, "message": "sent to pianist@example.com"}]},
        }
    )
    assert event["user"] == {"id": "42"}
    request = event["request"]
    assert request["url"] == "https://api.example.com/login"
    assert request["query_string"] == "[scrubbed]"
    assert set(request["headers"]) == {"Accept"}
    assert "cookies" not in request and "data" not in request and "env" not in request
    crumb = event["breadcrumbs"]["values"][0]
    assert crumb["data"]["url"] == "https://x.test/a"
    assert crumb["message"] == "sent to [email]"


def test_captured_exceptions_leave_no_personal_data(reporting):
    email = "@".join(["pianist", "example.com"])
    address = ".".join(["203", "0", "113", "9"])
    sentry_sdk.set_user({"id": "user-1", "email": email, "ip_address": address})
    try:
        raise ValueError(f"could not load {email}")
    except ValueError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()
    payload = json.dumps(reporting)
    assert reporting and reporting[0]["user"] == {"id": "user-1"}
    assert email not in payload
    assert address not in payload


async def test_a_failing_request_is_reported_without_its_body_or_credentials(reporting, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    class Exploding:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("database fell over")

    async def broken():
        yield Exploding()

    app.dependency_overrides[get_session] = broken
    transport = ASGITransport(app=app, raise_app_exceptions=False, client=("203.0.113.9", 5000))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post(
            "/api/v1/auth/token?email=pianist@example.com",
            json={"email": "pianist@example.com", "password": "hunter2222"},
            headers={"Authorization": "Bearer secret-token-value", "Cookie": "session=abc"},
        )
    sentry_sdk.flush()
    assert response.status_code == 500
    errors = [event for event in reporting if event.get("exception")]
    assert errors, "the failure should have been reported"
    payload = json.dumps(errors)
    for leak in ("pianist@example.com", "hunter2222", "secret-token-value", "session=abc", "203.0.113.9"):
        assert leak not in payload
    assert errors[0]["tags"]["component"] == "test"

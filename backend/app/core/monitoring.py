from __future__ import annotations

import inspect
import logging
import os
import re
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("piano.monitoring")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
SENSITIVE_KEY = re.compile(r"(?i)pass(word)?|secret|token|authorization|cookie|api[_-]?key|dsn|e-?mail|credential|session[_-]?id")
DROPPED_HEADERS = {"authorization", "cookie", "set-cookie", "x-forwarded-for", "x-real-ip", "forwarded", "cf-connecting-ip", "true-client-ip"}
SCRUBBED = "[scrubbed]"


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return BEARER.sub("Bearer " + SCRUBBED, EMAIL.sub("[email]", value))
    if isinstance(value, dict):
        return {key: SCRUBBED if isinstance(key, str) and SENSITIVE_KEY.search(key) else scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value


def scrub_request(request: dict) -> dict:
    cleaned = {key: value for key, value in request.items() if key not in {"cookies", "data", "env"}}
    headers = request.get("headers") or {}
    if isinstance(headers, dict):
        cleaned["headers"] = {key: value for key, value in headers.items() if key.lower() not in DROPPED_HEADERS}
    if cleaned.get("query_string"):
        cleaned["query_string"] = SCRUBBED
    if isinstance(cleaned.get("url"), str):
        cleaned["url"] = cleaned["url"].split("?", 1)[0]
    return cleaned


def scrub_breadcrumb(crumb: dict, hint: Optional[dict] = None) -> dict:
    data = crumb.get("data")
    if isinstance(data, dict) and isinstance(data.get("url"), str):
        data["url"] = data["url"].split("?", 1)[0]
    return scrub(crumb)


def scrub_event(event: dict, hint: Optional[dict] = None) -> dict:
    user = event.get("user") or {}
    event["user"] = {"id": str(user["id"])} if user.get("id") else {}
    if isinstance(event.get("request"), dict):
        event["request"] = scrub_request(event["request"])
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        breadcrumbs["values"] = [scrub_breadcrumb(crumb) for crumb in breadcrumbs.get("values") or []]
    return scrub(event)


def privacy_options() -> dict:
    from sentry_sdk.consts import ClientConstructor

    if "data_collection" in inspect.signature(ClientConstructor.__init__).parameters:
        return {"data_collection": {"user_info": False, "http_bodies": [], "stack_frame_variables": False}}
    return {"send_default_pii": False}


def init_sentry(component: str = "api", **overrides: Any) -> bool:
    dsn = (overrides.pop("dsn", None) or settings.sentry_dsn or "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment or settings.environment,
        release=os.environ.get("RENDER_GIT_COMMIT") or None,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub_event,
        before_send_transaction=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        **privacy_options(),
        **overrides,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("error reporting enabled for %s", component)
    return True


def identify(user_id: Any) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.set_user({"id": str(user_id)})

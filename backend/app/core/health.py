from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from app.core.config import settings

logger = logging.getLogger("piano.health")

TIMEOUT_SECONDS = 3.0


def redis_required() -> bool:
    return settings.job_queue == "redis" or settings.rate_limit_storage == "redis"


async def ping_database() -> bool:
    from app.core.database import ping

    return await ping()


async def ping_redis() -> bool:
    from redis.asyncio import Redis

    client = Redis.from_url(settings.redis_url, socket_connect_timeout=TIMEOUT_SECONDS, socket_timeout=TIMEOUT_SECONDS)
    try:
        return bool(await client.ping())
    finally:
        await client.aclose()


async def run_check(name: str, probe: Callable[[], Awaitable[bool]]) -> dict:
    started = time.perf_counter()
    try:
        ok = bool(await asyncio.wait_for(probe(), timeout=TIMEOUT_SECONDS))
    except asyncio.TimeoutError:
        logger.warning("health check %s timed out", name)
        ok = False
    except Exception:
        logger.warning("health check %s failed", name, exc_info=True)
        ok = False
    return {"ok": ok, "ms": round((time.perf_counter() - started) * 1000, 1)}


async def health_report(
    database: Optional[Callable[[], Awaitable[bool]]] = None,
    redis: Optional[Callable[[], Awaitable[bool]]] = None,
) -> tuple[bool, dict]:
    probes = {"database": database or ping_database}
    if redis_required():
        probes["redis"] = redis or ping_redis
    results = await asyncio.gather(*(run_check(name, probe) for name, probe in probes.items()))
    checks = dict(zip(probes, results))
    if "redis" not in checks:
        checks["redis"] = {"ok": None, "skipped": "not used in this configuration"}
    healthy = all(check["ok"] for check in checks.values() if check["ok"] is not None)
    return healthy, {
        "status": "ok" if healthy else "unavailable",
        "environment": settings.environment,
        "checks": checks,
    }

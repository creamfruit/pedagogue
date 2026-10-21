from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger("piano.rate_limit")

PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
RULE = re.compile(r"^\s*(\d+)\s*(?:/|per)\s*(\d*)\s*(second|minute|hour|day)s?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Limit:
    count: int
    seconds: int

    @classmethod
    def parse(cls, text: str) -> Limit:
        found = RULE.match(text or "")
        if not found:
            raise ValueError(f"rate limit {text!r} should look like '10/minute' or '100/day'")
        count, multiple, unit = found.groups()
        return cls(int(count), PERIODS[unit.lower()] * int(multiple or 1))


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


class MemoryBackend:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.counts: dict[str, tuple[int, float]] = {}
        self.lock = asyncio.Lock()

    async def hit(self, key: str, limit: Limit) -> tuple[int, int]:
        now = self.clock()
        window = math.floor(now / limit.seconds)
        bucket = f"{key}:{window}"
        reset = int((window + 1) * limit.seconds - now) or 1
        async with self.lock:
            if len(self.counts) > 50_000:
                self.counts = {k: v for k, v in self.counts.items() if v[1] > now}
            count = self.counts.get(bucket, (0, 0.0))[0] + 1
            self.counts[bucket] = (count, (window + 1) * limit.seconds)
        return count, reset

    def reset(self) -> None:
        self.counts.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self.redis = Redis.from_url(url)

    async def hit(self, key: str, limit: Limit) -> tuple[int, int]:
        now = time.time()
        window = math.floor(now / limit.seconds)
        bucket = f"pedagogue:rl:{key}:{window}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, limit.seconds + 1)
            count, _ = await pipe.execute()
        return int(count), int((window + 1) * limit.seconds - now) or 1


class RateLimiter:
    def __init__(self, backend=None) -> None:
        self.backend = backend
        self.fallback = MemoryBackend()

    def _backend(self):
        if self.backend is None:
            self.backend = RedisBackend(settings.redis_url) if settings.rate_limit_storage == "redis" else self.fallback
        return self.backend

    def limit_for(self, name: str) -> Limit:
        return Limit.parse(getattr(settings, f"rate_limit_{name}"))

    async def check(self, name: str, *identities: Optional[str]) -> None:
        if not settings.rate_limit_enabled:
            return
        limit = self.limit_for(name)
        for identity in identities:
            if not identity:
                continue
            key = f"{name}:{identity}"
            try:
                count, reset = await self._backend().hit(key, limit)
            except Exception:
                logger.warning("rate limit store unavailable, counting in memory", exc_info=True)
                count, reset = await self.fallback.hit(key, limit)
            if count > limit.count:
                raise RateLimited(reset)

    def reset(self) -> None:
        self.fallback.reset()
        if isinstance(self.backend, MemoryBackend):
            self.backend.reset()


limiter = RateLimiter()

MESSAGES = {
    "sign_in": "Too many sign-in attempts. Wait a little and try again.",
    "sign_in_ip": "Too many sign-in attempts from this network. Wait a little and try again.",
    "register": "Too many new accounts from this network. Try again later.",
    "upload": "You've uploaded a lot in a short time. Try again later.",
    "pdf_analysis": "You've sent a lot of scores to be read in a short time. Try again later.",
    "keyboard_attempt": "You've saved a lot of keyboard runs in a short time. Take a breather and try again soon.",
    "billing": "You've opened billing a lot in a short time. Try again later.",
}


def validate_limits() -> None:
    for name in MESSAGES:
        limiter.limit_for(name)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce(name: str, *identities: Optional[str]) -> None:
    try:
        await limiter.check(name, *identities)
    except RateLimited as limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=MESSAGES.get(name, "Too many requests. Try again later."),
            headers={"Retry-After": str(limited.retry_after)},
        )

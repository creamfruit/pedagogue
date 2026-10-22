import hashlib
import json
import os
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse

import httpx

from . import config

RETRY_STATUSES = {429, 500, 502, 503, 504}
ROBOTS_MAX_AGE_SECONDS = 24 * 3600
DEFAULT_MAX_BYTES = 64 * 1024 * 1024


class FetchError(Exception):
    pass


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    headers: dict = field(default_factory=dict)
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def full_url(url: str, params: Optional[dict] = None) -> str:
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(sorted(params.items()))}"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


class PoliteClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        user_agent: str = config.USER_AGENT,
        intervals: Optional[dict] = None,
        default_interval: float = config.DEFAULT_MIN_INTERVAL,
        timeout: float = 30.0,
        retries: int = 4,
        backoff: float = 2.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        robots_hosts: tuple = ("www.mutopiaproject.org",),
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.intervals = dict(config.MIN_INTERVAL_SECONDS if intervals is None else intervals)
        self.default_interval = default_interval
        self.retries = retries
        self.backoff = backoff
        self.max_bytes = max_bytes
        self.sleep = sleep
        self.clock = clock
        self.wall = wall
        self.robots_hosts = set(robots_hosts)
        self.requests_made = 0
        self.cache_hits = 0
        self._last: dict[str, float] = {}
        self._robots: dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def paths(self, url: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        host = urlparse(url).netloc or "local"
        folder = self.cache_dir / "http" / host / digest[:2]
        return folder / f"{digest}.body", folder / f"{digest}.json"

    def wait(self, host: str) -> None:
        interval = self.intervals.get(host, self.default_interval)
        last = self._last.get(host)
        if last is not None:
            remaining = interval - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def cached(self, url: str, max_age: Optional[float]) -> Optional[Response]:
        body_path, meta_path = self.paths(url)
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            body = body_path.read_bytes() if body_path.exists() else b""
        except (OSError, ValueError):
            return None
        if max_age is not None and self.wall() - meta.get("fetched_at", 0) > max_age:
            return None
        return Response(url, meta["status"], body, meta.get("headers", {}), True)

    def stale(self, url: str) -> Optional[dict]:
        _, meta_path = self.paths(url)
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def store(self, url: str, status: int, body: bytes, headers: dict) -> None:
        body_path, meta_path = self.paths(url)
        atomic_write(body_path, body)
        keep = {key: value for key, value in headers.items() if key in {"etag", "last-modified", "content-type"}}
        meta = {"url": url, "status": status, "headers": keep, "fetched_at": self.wall(), "bytes": len(body)}
        atomic_write(meta_path, json.dumps(meta).encode("utf-8"))

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc not in self.robots_hosts:
            return True
        if parsed.path == "/robots.txt":
            return True
        if parsed.netloc not in self._robots:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            reply = self.get(robots_url, max_age=ROBOTS_MAX_AGE_SECONDS)
            if reply.status == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(reply.text.splitlines())
                self._robots[parsed.netloc] = parser
            else:
                self._robots[parsed.netloc] = None
        parser = self._robots[parsed.netloc]
        return parser is None or parser.can_fetch(config.USER_AGENT, url)

    def send(self, url: str, headers: Optional[dict] = None) -> httpx.Response:
        host = urlparse(url).netloc
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            self.wait(host)
            self.requests_made += 1
            try:
                reply = self._client.get(url, headers=headers or {})
            except httpx.TransportError as error:
                last_error = error
                self.sleep(self.backoff ** (attempt + 1))
                continue
            if reply.status_code in RETRY_STATUSES:
                last_error = FetchError(f"{url} answered {reply.status_code}")
                pause = reply.headers.get("retry-after", "")
                self.sleep(float(pause) if pause.isdigit() else self.backoff ** (attempt + 1))
                continue
            return reply
        raise FetchError(f"{url} failed after {self.retries + 1} attempts: {last_error}")

    def get(self, url: str, *, params: Optional[dict] = None, max_age: Optional[float] = None, refresh: bool = False) -> Response:
        target = full_url(url, params)
        if not refresh:
            held = self.cached(target, max_age)
            if held is not None:
                self.cache_hits += 1
                return held
        if not self.allowed(target):
            raise FetchError(f"{target} is disallowed by robots.txt")
        conditions = {}
        previous = self.stale(target)
        if previous and previous.get("status") == 200:
            if previous["headers"].get("etag"):
                conditions["If-None-Match"] = previous["headers"]["etag"]
            if previous["headers"].get("last-modified"):
                conditions["If-Modified-Since"] = previous["headers"]["last-modified"]
        reply = self.send(target, conditions)
        if reply.status_code == 304 and previous:
            body_path, meta_path = self.paths(target)
            previous["fetched_at"] = self.wall()
            atomic_write(meta_path, json.dumps(previous).encode("utf-8"))
            held = self.cached(target, None)
            if held is not None:
                return held
        if reply.status_code in {404, 410}:
            self.store(target, reply.status_code, b"", {})
            return Response(target, reply.status_code, b"", {}, False)
        if reply.status_code >= 400:
            raise FetchError(f"{target} answered {reply.status_code}")
        if len(reply.content) > self.max_bytes:
            raise FetchError(f"{target} is larger than {self.max_bytes} bytes")
        headers = {key.lower(): value for key, value in reply.headers.items()}
        self.store(target, reply.status_code, reply.content, headers)
        return Response(target, reply.status_code, reply.content, headers, False)

    def download(self, url: str, destination: Path) -> Path:
        destination = Path(destination)
        if destination.exists():
            self.cache_hits += 1
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        host = urlparse(url).netloc
        for attempt in range(self.retries + 1):
            have = partial.stat().st_size if partial.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            self.wait(host)
            self.requests_made += 1
            try:
                with self._client.stream("GET", url, headers=headers) as reply:
                    if reply.status_code == 416:
                        partial.unlink(missing_ok=True)
                        continue
                    if reply.status_code in RETRY_STATUSES:
                        self.sleep(self.backoff ** (attempt + 1))
                        continue
                    if reply.status_code >= 400:
                        raise FetchError(f"{url} answered {reply.status_code}")
                    mode = "ab" if reply.status_code == 206 and have else "wb"
                    with open(partial, mode) as handle:
                        for chunk in reply.iter_bytes(1 << 20):
                            handle.write(chunk)
                os.replace(partial, destination)
                return destination
            except httpx.TransportError:
                self.sleep(self.backoff ** (attempt + 1))
        raise FetchError(f"{url} could not be downloaded after {self.retries + 1} attempts")

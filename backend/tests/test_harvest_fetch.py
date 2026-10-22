import httpx
import pytest

from tools.harvest.polite import FetchError, PoliteClient


class FakeClock:
    def __init__(self):
        self.now_value = 1000.0
        self.pauses = []

    def now(self):
        return self.now_value

    def wall(self):
        return self.now_value

    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now_value += seconds


def build(tmp_path, handler, clock=None, **options):
    clock = clock or FakeClock()
    client = PoliteClient(
        tmp_path,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.now,
        wall=clock.wall,
        **options,
    )
    return client, clock


def test_a_second_request_for_the_same_page_is_served_from_disk(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="catalogue")

    client, _ = build(tmp_path, handler)
    first = client.get("https://example.test/page")
    second = client.get("https://example.test/page")
    assert first.text == second.text == "catalogue"
    assert second.from_cache and not first.from_cache
    assert len(calls) == 1


def test_a_new_client_reuses_the_cache_so_an_interrupted_run_resumes(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text="kept")

    build(tmp_path, handler)[0].get("https://example.test/a")
    resumed, _ = build(tmp_path, handler)
    assert resumed.get("https://example.test/a").text == "kept"
    assert len(calls) == 1


def test_requests_to_one_host_are_spaced_out(tmp_path):
    client, clock = build(tmp_path, lambda request: httpx.Response(200, text="x"), intervals={"example.test": 2.0})
    client.get("https://example.test/one")
    client.get("https://example.test/two")
    client.get("https://example.test/three")
    assert len(clock.pauses) == 2
    assert all(pause >= 2.0 - 1e-9 for pause in clock.pauses)


def test_different_hosts_are_throttled_separately(tmp_path):
    client, clock = build(tmp_path, lambda request: httpx.Response(200, text="x"), intervals={"a.test": 5.0, "b.test": 5.0})
    client.get("https://a.test/")
    client.get("https://b.test/")
    assert clock.pauses == []


def test_a_busy_server_is_retried_with_its_retry_after_wait(tmp_path):
    replies = [httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200, text="done")]
    client, clock = build(tmp_path, lambda request: replies.pop(0))
    assert client.get("https://example.test/").text == "done"
    assert 7.0 in clock.pauses


def test_gives_up_after_the_retries_are_spent(tmp_path):
    client, _ = build(tmp_path, lambda request: httpx.Response(503), retries=2)
    with pytest.raises(FetchError):
        client.get("https://example.test/")
    assert client.requests_made == 3


def test_a_missing_page_is_remembered(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)

    client, _ = build(tmp_path, handler)
    assert client.get("https://example.test/gone").status == 404
    assert client.get("https://example.test/gone").status == 404
    assert len(calls) == 1


def test_an_expired_page_is_revalidated_and_a_304_keeps_the_cached_body(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers.get("if-none-match"))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text="body", headers={"etag": '"v1"'})

    client, clock = build(tmp_path, handler)
    client.get("https://example.test/p", max_age=60)
    clock.now_value += 3600
    again = client.get("https://example.test/p", max_age=60)
    assert again.text == "body"
    assert seen == [None, '"v1"']


def test_the_harvester_names_itself_to_servers(tmp_path):
    agents = []

    def handler(request):
        agents.append(request.headers["user-agent"])
        return httpx.Response(200, text="x")

    client, _ = build(tmp_path, handler)
    client.get("https://example.test/")
    assert agents[0].startswith("PedagogueHarvester/")
    assert "http" in agents[0]


def test_a_partial_download_resumes_where_it_stopped(tmp_path):
    payload = bytes(range(256)) * 40
    ranges = []

    def handler(request):
        header = request.headers.get("range")
        ranges.append(header)
        if header:
            start = int(header.split("=")[1].split("-")[0])
            return httpx.Response(206, content=payload[start:])
        return httpx.Response(200, content=payload)

    client, _ = build(tmp_path, handler)
    target = tmp_path / "dl" / "archive.zip"
    target.parent.mkdir()
    (target.parent / "archive.zip.part").write_bytes(payload[:1000])
    client.download("https://example.test/archive.zip", target)
    assert target.read_bytes() == payload
    assert ranges == ["bytes=1000-"]
    assert not (target.parent / "archive.zip.part").exists()


def test_a_finished_download_is_not_fetched_again(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b"data")

    client, _ = build(tmp_path, handler)
    target = tmp_path / "file.bin"
    client.download("https://example.test/file.bin", target)
    client.download("https://example.test/file.bin", target)
    assert len(calls) == 1


def test_robots_txt_is_obeyed_on_scraped_hosts(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="ok")

    client, _ = build(tmp_path, handler, robots_hosts=("example.test",))
    assert client.get("https://example.test/public").text == "ok"
    with pytest.raises(FetchError):
        client.get("https://example.test/private/page")


def test_a_site_without_robots_txt_is_allowed(tmp_path):
    def handler(request):
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, text="ok")

    client, _ = build(tmp_path, handler, robots_hosts=("example.test",))
    assert client.get("https://example.test/anything").text == "ok"


def test_parameters_make_distinct_cache_entries(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=str(request.url.query))

    client, _ = build(tmp_path, handler)
    one = client.get("https://example.test/list", params={"startat": 0})
    two = client.get("https://example.test/list", params={"startat": 10})
    assert one.text != two.text
    assert len(calls) == 2

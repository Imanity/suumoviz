import pytest
from helpers import FakeClock, FakeSuumo, make_fetcher

from suumoviz.fetch import (
    Blocked,
    BudgetExceeded,
    PageError,
    Response,
    TransportError,
    looks_like_challenge,
)

LIST_URL = "https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?pc=100&po=3&pj=1"


def test_requests_start_at_least_five_seconds_apart() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    fetcher = make_fetcher(server, clock)
    for _ in range(4):
        assert fetcher.get(LIST_URL).status == 200
    starts = [t for t, _, _ in server.calls]
    assert all(b - a >= 5.0 for a, b in zip(starts, starts[1:], strict=False))
    assert fetcher.requests == 4


def test_user_agent_names_the_crawler_and_no_cookies() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    make_fetcher(server, clock).get(LIST_URL)
    headers = server.calls[0][2]
    assert headers["User-Agent"] == "Mozilla/5.0 (compatible; SuumoViz/0.1.0)"
    assert headers["Accept-Encoding"] == "gzip"
    assert "Cookie" not in headers


@pytest.mark.parametrize("status", [401, 403, 429])
def test_block_statuses_raise_blocked(status: int) -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    server.override = lambda n, url: Response(url, status, b"", {"Retry-After": "120"})
    with pytest.raises(Blocked) as info:
        make_fetcher(server, clock).get(LIST_URL)
    assert info.value.reason == f"http_{status}"
    assert info.value.retry_after == 120
    assert len(server.calls) == 1  # never retried


def test_challenge_page_raises_blocked() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    server.override = lambda n, url: Response(url, 200, b"<div class='g-recaptcha'></div>")
    with pytest.raises(Blocked) as info:
        make_fetcher(server, clock).get(LIST_URL)
    assert info.value.reason == "challenge_page"


def test_real_fixtures_are_not_challenges(fixture_bytes) -> None:
    from helpers import FIXTURES

    for path in FIXTURES.glob("*.html"):
        assert not looks_like_challenge(fixture_bytes(path.name)), path.name


def test_server_errors_are_retried_then_fail() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    server.override = lambda n, url: Response(url, 503, b"") if n < 3 else None
    fetcher = make_fetcher(server, clock)
    assert fetcher.get(LIST_URL).status == 200
    assert len(server.calls) == 3
    starts = [t for t, _, _ in server.calls]
    assert starts[1] - starts[0] >= 30 and starts[2] - starts[1] >= 60

    server.override = lambda n, url: Response(url, 500, b"")
    with pytest.raises(PageError) as info:
        fetcher.get(LIST_URL)
    assert info.value.reason == "http_500"


def test_network_errors_are_retried() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)

    def flaky(n: int, url: str) -> Response | None:
        if n == 1:
            raise TransportError("timed out")
        return None

    server.override = flaky
    assert make_fetcher(server, clock).get(LIST_URL).status == 200


def test_client_errors_are_not_retried() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    with pytest.raises(PageError) as info:
        make_fetcher(server, clock).get("https://suumo.jp/unknown/")
    assert info.value.reason == "http_404"
    assert len(server.calls) == 1


def test_request_and_time_budgets() -> None:
    clock = FakeClock()
    server = FakeSuumo(clock)
    fetcher = make_fetcher(server, clock, max_requests=2)
    fetcher.get(LIST_URL)
    fetcher.get(LIST_URL)
    with pytest.raises(BudgetExceeded) as info:
        fetcher.get(LIST_URL)
    assert info.value.reason == "request_budget"

    fetcher = make_fetcher(server, clock, max_seconds=12)
    fetcher.get(LIST_URL)
    fetcher.get(LIST_URL)
    fetcher.get(LIST_URL)
    with pytest.raises(BudgetExceeded) as info:
        fetcher.get(LIST_URL)
    assert info.value.reason == "time_budget"

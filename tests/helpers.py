"""Fake clock and fake SUUMO server for offline crawler tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from suumoviz import codec
from suumoviz.fetch import Fetcher, Response

FIXTURES = Path(__file__).parent / "fixtures" / "suumo"

LIST_FIXTURES = {
    "ms/chuko": "list_used_condo_setagaya_p1.html",
    "ms/shinchiku": "list_new_condo_chuo_p1.html",
    "ikkodate": "list_new_house_setagaya_p1.html",
    "chukoikkodate": "list_used_house_setagaya_p1.html",
}
CITY_FIXTURES = {
    "ms/chuko": "city_used_condo.html",
    "ms/shinchiku": "city_new_condo.html",
    "ikkodate": "city_new_house.html",
    "chukoikkodate": "city_used_house.html",
}


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.t += seconds


class FakeSuumo:
    """Serves fixtures by URL; ``override`` can replace the response for the n-th call."""

    def __init__(self, clock: FakeClock, robots: str | None = None) -> None:
        self.clock = clock
        self.calls: list[tuple[float, str, dict[str, str]]] = []
        self.robots = robots
        self.override: Callable[[int, str], Response | None] = lambda n, url: None

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> Response:
        self.calls.append((self.clock.time(), url, headers))
        self.clock.t += 0.5  # response time
        replaced = self.override(len(self.calls), url)
        if replaced is not None:
            return replaced
        path = url.split("suumo.jp/", 1)[1]
        if path == "robots.txt":
            body = (self.robots or codec.read_text(FIXTURES / "robots.txt")).encode()
            return Response(url, 200, body)
        for prefix, name in CITY_FIXTURES.items():
            if path.startswith(f"{prefix}/tokyo/city/"):
                return Response(url, 200, codec.read_bytes(FIXTURES / name))
        for prefix, name in LIST_FIXTURES.items():
            if path.startswith(f"{prefix}/tokyo/sc_"):
                return Response(url, 200, codec.read_bytes(FIXTURES / name))
        return Response(url, 404, b"not found")

    @property
    def urls(self) -> list[str]:
        return [url for _, url, _ in self.calls]


def make_fetcher(server: FakeSuumo, clock: FakeClock, **kwargs: object) -> Fetcher:
    return Fetcher(
        transport=server,
        clock=clock.time,
        sleep=clock.sleep,
        **kwargs,  # type: ignore[arg-type]
    )

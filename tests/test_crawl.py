import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from helpers import FIXTURES, FakeClock, FakeSuumo, make_fetcher

from suumoviz import codec
from suumoviz.crawl import CrawlOptions, run_crawl
from suumoviz.fetch import Response
from suumoviz.state import JST, State
from suumoviz.store import read_rows

DAY = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 3, 17, tzinfo=JST)


def options(tmp_path: Path, **kwargs: object) -> CrawlOptions:
    return CrawlOptions(day=DAY, data_dir=tmp_path / "data", work_dir=tmp_path / "work", **kwargs)


def read_csv(path: Path) -> list[dict[str, str]]:
    assert codec.is_encoded(path.read_bytes()), f"{path.name} must be stored obfuscated"
    return read_rows(path)


@pytest.fixture
def env():
    clock = FakeClock()
    server = FakeSuumo(clock)
    return clock, server


def test_full_run_writes_snapshot_and_state(tmp_path: Path, env) -> None:
    clock, server = env
    fetcher = make_fetcher(server, clock)
    result = run_crawl(options(tmp_path), fetcher, now=lambda: NOW, log=lambda _: None)

    assert result.status == "completed" and result.exit_code == 0
    assert server.urls[0] == "https://suumo.jp/robots.txt"
    assert all("/tokyo/city/" in u for u in server.urls[1:5])
    list_urls = server.urls[5:]
    assert 95 <= len(list_urls) <= 105
    assert len(server.urls) == fetcher.requests == result.summary["requests"]

    out = tmp_path / "work" / "2026-11-07"
    counts = read_csv(out / "counts.csv")
    assert len({(r["category"], r["area_code"]) for r in counts}) == len(counts)
    assert sum(int(r["count"]) for r in counts if r["category"] == "used_condo") == 36_894
    pages = read_csv(out / "pages.csv")
    assert len(pages) == len(list_urls)
    assert {p["status"] for p in pages} == {"ok"}
    listings = read_csv(out / "listings.csv")
    assert len(listings) == result.summary["listings"] > 0
    assert {"listing_id", "price_min", "area_code", "page"} <= set(listings[0])
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "completed" and run["slot"] == 5

    state = State.load(tmp_path / "data" / "state.json")
    assert len(state.offsets) == 193
    assert state.robots_sha256 and state.cooldown_until is None
    assert state.last_run["status"] == "completed"


def test_second_run_reuses_offsets(tmp_path: Path, env) -> None:
    clock, server = env
    run_crawl(options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None)
    first = State.load(tmp_path / "data" / "state.json").offsets
    next_day = CrawlOptions(
        day=DAY + timedelta(days=1), data_dir=tmp_path / "data", work_dir=tmp_path / "work"
    )
    run_crawl(next_day, make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None)
    assert State.load(tmp_path / "data" / "state.json").offsets == first


def test_block_mid_run_sets_cooldown_and_next_run_skips(tmp_path: Path, env) -> None:
    clock, server = env
    server.override = lambda n, url: Response(url, 403, b"") if n == 8 else None
    result = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None
    )
    assert result.status == "blocked" and result.exit_code == 2
    assert result.stop_reason == "http_403"
    assert len(server.calls) == 8  # stopped right away

    state = State.load(tmp_path / "data" / "state.json")
    assert state.cooldown_until == NOW + timedelta(hours=24)
    pages = read_csv(tmp_path / "work" / "2026-11-07" / "pages.csv")
    assert [p["status"] for p in pages][-1] == "blocked"
    assert sum(p["status"] == "ok" for p in pages) == 2

    calls_before = len(server.calls)
    later = NOW + timedelta(hours=12)
    skipped = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: later, log=lambda _: None
    )
    assert skipped.status == "skipped" and skipped.exit_code == 0
    assert len(server.calls) == calls_before  # no request during cooldown

    after = NOW + timedelta(hours=25)
    resumed = run_crawl(
        options(tmp_path, max_pages=1),
        make_fetcher(server, clock),
        now=lambda: after,
        log=lambda _: None,
    )
    assert resumed.status == "limited"


def test_repeat_block_within_a_week_cools_down_longer(tmp_path: Path, env) -> None:
    clock, server = env
    server.override = lambda n, url: Response(url, 429, b"") if url.endswith("robots.txt") else None
    run_crawl(options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None)
    later = NOW + timedelta(days=2)
    run_crawl(options(tmp_path), make_fetcher(server, clock), now=lambda: later, log=lambda _: None)
    state = State.load(tmp_path / "data" / "state.json")
    assert state.cooldown_until == later + timedelta(hours=72)
    assert len(state.blocks) == 2


def test_challenge_page_blocks(tmp_path: Path, env) -> None:
    clock, server = env
    server.override = lambda n, url: (
        Response(url, 200, b"<p>captcha</p>") if "/sc_" in url else None
    )
    result = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None
    )
    assert result.status == "blocked" and result.stop_reason == "challenge_page"


def test_robots_disallowing_targets_stops_before_list_pages(tmp_path: Path, env) -> None:
    clock, server = env
    server.robots = "User-agent: *\nDisallow: /ms/chuko/tokyo/sc_\n"
    result = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None
    )
    assert result.status == "blocked" and result.stop_reason == "robots_disallow"
    assert not any("/sc_" in u for u in server.urls)


def test_consecutive_page_failures_stop_the_run(tmp_path: Path, env) -> None:
    clock, server = env
    server.override = lambda n, url: Response(url, 404, b"") if "/sc_" in url else None
    result = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None
    )
    assert result.status == "partial" and result.exit_code == 1
    assert result.stop_reason == "consecutive_page_failures"
    assert sum("/sc_" in u for u in server.urls) == 3


def test_unknown_layout_counts_as_failure(tmp_path: Path, env) -> None:
    clock, server = env
    server.override = lambda n, url: (
        Response(url, 200, b"<html><body>new design</body></html>") if "/sc_" in url else None
    )
    result = run_crawl(
        options(tmp_path), make_fetcher(server, clock), now=lambda: NOW, log=lambda _: None
    )
    assert result.status == "partial" and result.stop_reason == "unknown_layout"


def test_max_pages_limits_list_requests(tmp_path: Path, env) -> None:
    clock, server = env
    result = run_crawl(
        options(tmp_path, max_pages=5),
        make_fetcher(server, clock),
        now=lambda: NOW,
        log=lambda _: None,
    )
    assert result.status == "limited" and result.exit_code == 0
    assert len(server.urls) == 5 + 5


def test_offline_dry_run_makes_no_requests_and_writes_nothing(tmp_path: Path) -> None:
    lines: list[str] = []
    result = run_crawl(
        options(tmp_path, dry_run=True, city_html_dir=FIXTURES),
        None,
        now=lambda: NOW,
        log=lines.append,
    )
    assert result.status == "planned"
    assert 95 <= result.summary["planned_pages"] <= 105
    assert lines[0].startswith("date 2026-11-07 (JST)  slot 5 of 7")
    assert any("requests" in line for line in lines)
    assert not (tmp_path / "data").exists() and not (tmp_path / "work").exists()

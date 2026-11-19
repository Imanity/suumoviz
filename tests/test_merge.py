import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from helpers import FakeClock, FakeSuumo, make_fetcher

from suumoviz.crawl import CrawlOptions, run_crawl
from suumoviz.merge import MergeError, merge_day
from suumoviz.state import JST
from suumoviz.store import read_rows

D0 = date(2026, 11, 2)
LISTING_COLUMNS = [
    "date", "area_code", "page", "listing_id", "category", "name", "price_min", "price_max",
    "price_raw", "address", "access_raw", "line", "station", "walk_min", "area_min", "area_max",
    "land_min", "land_max", "layout", "balcony", "built_ym", "delivery_raw", "labels",
]  # fmt: skip
PAGE_COLUMNS = [
    "date", "category", "area_code", "page", "pages", "url", "status", "error",
    "expected_total", "total", "items", "fetched_at",
]  # fmt: skip


def listing(
    listing_id: str,
    *,
    category: str = "used_condo",
    area: str = "13112",
    price: int | None = 50_000_000,
    area_min: float | None = 50.0,
    land: float | None = None,
    address: str = "東京都世田谷区三宿1",
) -> dict[str, str]:
    return {
        "listing_id": listing_id,
        "category": category,
        "area_code": area,
        "page": "1",
        "price_min": "" if price is None else str(price),
        "price_max": "" if price is None else str(price),
        "price_raw": "未定" if price is None else f"{price // 10_000}万円",
        "address": address,
        "area_min": "" if area_min is None else str(area_min),
        "area_max": "" if area_min is None else str(area_min),
        "land_min": "" if land is None else str(land),
        "station": "三軒茶屋",
    }


def write_snapshot(
    work: Path,
    day: date,
    listings: list[dict[str, str]],
    *,
    status: str = "completed",
    pages: list[dict[str, str]] | None = None,
) -> Path:
    out = work / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    if pages is None:
        combos: dict[tuple[str, str], int] = {}
        for row in listings:
            combos[(row["category"], row["area_code"])] = combos.get(
                (row["category"], row["area_code"]), 0) + 1  # fmt: skip
        pages = [
            {
                "category": c,
                "area_code": a,
                "page": "1",
                "pages": "1",
                "status": "ok",
                "expected_total": str(n),
                "total": str(n),
                "items": str(n),
            }  # fmt: skip
            for (c, a), n in combos.items()
        ]
    with (out / "listings.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, LISTING_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**r, "date": day.isoformat()} for r in listings)
    with (out / "pages.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, PAGE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**p, "date": day.isoformat()} for p in pages)
    with (out / "counts.csv").open("w", encoding="utf-8", newline="") as fh:
        fh.write("date,category,area_code,area_name,slug,count\n")
        fh.write(f"{day},used_condo,13112,世田谷区,sc_setagaya,{len(listings)}\n")
    run = {"date": day.isoformat(), "slot": 0, "status": status, "stop_reason": None,
           "requests": 10, "planned_pages": len(pages), "fetched_pages": len(pages),
           "failed_pages": 0, "listings": len(listings)}  # fmt: skip
    (out / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return out


def table(data: Path, category: str = "used_condo") -> dict[str, dict[str, str]]:
    return {r["listing_id"]: r for r in read_rows(data / "listings" / f"{category}.csv")}


def events(data: Path, day: date) -> list[dict[str, str]]:
    return read_rows(data / "events" / f"{day.isoformat()[:7]}.csv")


def test_first_merge_creates_tables(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    snap = write_snapshot(work, D0, [listing("1"), listing("2"), listing("3")])
    result = merge_day(data, snap)

    assert result.merged and result.exit_code == 0
    assert result.events == {"new": 3, "price_change": 0, "delisted": 0, "relisted": 0}
    rows = table(data)
    assert set(rows) == {"1", "2", "3"}
    assert rows["1"]["status"] == "active"
    assert rows["1"]["first_seen"] == rows["1"]["last_seen"] == "2026-11-02"
    assert [e["type"] for e in events(data, D0)] == ["new"] * 3
    run = read_rows(data / "runs.csv")
    assert run[0]["merged"] == "true" and run[0]["new"] == "3" and run[0]["slot"] == "0"
    assert len(read_rows(data / "counts" / "2026.csv")) == 1
    scopes = {r["scope"] for r in read_rows(data / "stats" / "2026.csv")}
    assert scopes == {"sample", "census"}


def test_remerge_same_day_changes_nothing(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    snap = write_snapshot(work, D0, [listing("1"), listing("2", price=None)])
    merge_day(data, snap)
    before = {p: p.read_bytes() for p in data.rglob("*.csv")}
    merge_day(data, snap)
    after = {p: p.read_bytes() for p in data.rglob("*.csv")}
    assert before == after


def test_price_change_is_recorded_with_old_and_new(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0, [listing("1", price=50_000_000)]))
    d1 = D0 + timedelta(days=7)
    result = merge_day(data, write_snapshot(work, d1, [listing("1", price=48_000_000)]))

    assert result.events["price_change"] == 1
    change = [e for e in events(data, d1) if e["type"] == "price_change"]
    assert change[0]["price_min_old"] == "50000000" and change[0]["price_min"] == "48000000"
    row = table(data)["1"]
    assert row["price_min"] == "48000000"
    assert row["last_price_change"] == d1.isoformat()
    assert row["first_seen"] == D0.isoformat() and row["last_seen"] == d1.isoformat()


def _run_days(data: Path, work: Path, days: range, statuses: dict[int, str] | None = None) -> None:
    for i in days:
        status = (statuses or {}).get(i, "completed")
        merge_day(data, write_snapshot(work, D0 + timedelta(days=i), [listing("B")], status=status))


def test_delisted_after_two_missed_cycles(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0, [listing("A"), listing("B")]))
    _run_days(data, work, range(1, 15))
    assert table(data)["A"]["status"] == "active"  # 14 days: not yet

    _run_days(data, work, range(15, 16))
    row = table(data)["A"]
    assert row["status"] == "inactive" and row["delisted_on"] == "2026-11-17"
    delisted = [e for e in events(data, D0 + timedelta(days=15)) if e["type"] == "delisted"]
    assert [e["listing_id"] for e in delisted] == ["A"]
    assert table(data)["B"]["status"] == "active"


def test_no_delisting_when_too_few_completed_runs(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0, [listing("A"), listing("B")]))
    _run_days(data, work, range(1, 16), statuses={3: "partial", 6: "blocked", 9: "limited"})
    assert table(data)["A"]["status"] == "active"  # only 12 completed runs since last seen
    _run_days(data, work, range(16, 17))
    assert table(data)["A"]["status"] == "inactive"


def test_relisted_listing(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0, [listing("A"), listing("B")]))
    _run_days(data, work, range(1, 16))
    d16 = D0 + timedelta(days=16)
    result = merge_day(data, write_snapshot(work, d16, [listing("A", price=45_000_000)]))
    assert result.events["relisted"] == 1 and result.events["price_change"] == 1
    row = table(data)["A"]
    assert row["status"] == "active" and row["delisted_on"] == ""


def test_quality_failure_keeps_tables_untouched(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    broken = [listing(str(i), address="") for i in range(25)]
    result = merge_day(data, write_snapshot(work, D0, broken))
    assert not result.merged and result.exit_code == 1
    assert "missing_address:used_condo" in result.quality.problems
    assert not (data / "listings").exists()
    run = read_rows(data / "runs.csv")[0]
    assert run["merged"] == "false" and "missing_address" in run["quality"]
    assert len(read_rows(data / "counts" / "2026.csv")) == 1  # counts still recorded


def test_quality_checks_page_totals_and_item_counts(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    pages = [{"category": "used_condo", "area_code": "13112", "page": "1", "pages": "2",
              "status": "ok", "expected_total": "150", "total": "230", "items": "40"}]  # fmt: skip
    result = merge_day(data, write_snapshot(work, D0, [listing("1")], pages=pages))
    problems = " ".join(result.quality.problems)
    assert "total_mismatch:used_condo:13112:p1:150->230" in problems
    assert "item_count_mismatch:1/1" not in problems  # a single mismatch is tolerated

    pages = [{**pages[0], "total": "150", "page": str(i)} for i in (1, 2, 3)]
    result = merge_day(data, write_snapshot(work, D0, [listing("1")], pages=pages))
    # 40 items on each page, but p1 should hold 100, p2 50 and p3 none
    assert "item_count_mismatch:3/3" in result.quality.problems


def test_merge_refuses_older_day(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0 + timedelta(days=1), [listing("1")]))
    with pytest.raises(MergeError):
        merge_day(data, write_snapshot(work, D0, [listing("1")]))


def test_stats_sample_and_census(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    condos = [listing(str(i), price=p, area_min=50.0)
              for i, p in enumerate([40_000_000, 50_000_000, 60_000_000, 70_000_000])]  # fmt: skip
    houses = [
        listing("h1", category="new_house", price=80_000_000, area_min=100.0, land=80.0),
        listing("h2", category="new_house", price=90_000_000, area_min=None, land=150.0),  # land
    ]
    new_condo = [listing("n1", category="new_condo", price=None, area_min=60.0)]
    merge_day(data, write_snapshot(work, D0, condos + houses + new_condo))

    rows = read_rows(data / "stats" / "2026.csv")
    stats = {(r["scope"], r["category"]): r for r in rows if r["area_code"] == "13112"}
    condo = stats[("sample", "used_condo")]
    assert condo["n"] == "4"
    assert (condo["price_p25"], condo["price_median"], condo["price_p75"]) == (
        "47500000", "55000000", "62500000",
    )  # fmt: skip
    assert condo["unit_n"] == "4" and condo["unit_price_median"] == "1100000"
    house = stats[("sample", "new_house")]
    assert house["n"] == "2" and house["unit_n"] == "1"  # land-only listing has no unit price
    assert house["unit_price_median"] == "800000"
    newc = stats[("census", "new_condo")]
    assert newc["n"] == "1" and newc["price_median"] == "" and newc["unit_n"] == "0"


def test_stats_include_prefecture_wide_rows(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    rows = [
        listing("1", area="13112", price=40_000_000),
        listing("2", area="13113", price=60_000_000),
        listing("3", area="13113", price=80_000_000),
    ]
    merge_day(data, write_snapshot(work, D0, rows))
    stats = {(r["scope"], r["area_code"]): r for r in read_rows(data / "stats" / "2026.csv")}
    for scope in ("sample", "census"):
        tokyo = stats[(scope, "13000")]
        assert tokyo["category"] == "used_condo"
        assert (tokyo["n"], tokyo["price_median"]) == ("3", "60000000")
        assert stats[(scope, "13113")]["n"] == "2"


def test_inactive_rows_pruned_after_retention(tmp_path: Path) -> None:
    data, work = tmp_path / "data", tmp_path / "work"
    merge_day(data, write_snapshot(work, D0, [listing("A"), listing("B")]))
    _run_days(data, work, range(1, 16))
    assert "A" in table(data)
    later = D0 + timedelta(days=15 + 91)
    merge_day(data, write_snapshot(work, later, [listing("B")]))
    assert "A" not in table(data)
    assert any(e["type"] == "delisted" for e in events(data, D0 + timedelta(days=15)))


def test_crawl_then_merge_rejects_truncated_pages(tmp_path: Path) -> None:
    """Fixture pages keep a few items but their headers claim 100+; the gate must notice."""
    clock = FakeClock()
    server = FakeSuumo(clock)
    options = CrawlOptions(day=date(2026, 11, 7), data_dir=tmp_path / "data",
                           work_dir=tmp_path / "work")  # fmt: skip
    now = datetime(2026, 11, 7, 3, 17, tzinfo=JST)
    run_crawl(options, make_fetcher(server, clock), now=lambda: now, log=lambda _: None)
    snapshot = read_rows(tmp_path / "work" / "2026-11-07" / "listings.csv")
    assert snapshot
    assert all(f"/nc_{r['listing_id']}/" in r["path"] for r in snapshot)  # detail path kept
    result = merge_day(tmp_path / "data", tmp_path / "work" / "2026-11-07")
    assert not result.merged
    assert any(p.startswith("item_count_mismatch") for p in result.quality.problems)

"""Web data: price statistics per area and day, built from the data tables.

Every output file is a JSON document obfuscated with ``codec`` (the page decodes it in the
browser). Only per-area aggregates are published, never single listings::

    {out}/index.dat                          timeline, categories, all-Tokyo series
    {out}/day/{date}/{category}.dat          every area's values on one day (the map)
    {out}/history/{category}/{parent}.dat    series of the areas under ``parent`` (trends)

Areas are the e-Stat census small areas (``Geocoder.area_codes``): municipality (5-digit
code), town (9) and chome or 字 (11); ``13000`` is all of Tokyo. The history file of a
municipality is under ``13000``, of a town under its municipality, of a chome under its
town.

A listing is on sale on day D when it was first seen on or before D and last seen less
than ``GRACE_DAYS`` before D (each page is rescanned every 7 days, a day later when
pagination drifts). Its price on D is the latest price event on or before D. Day D is on
the timeline once the ``GRACE_DAYS`` before it were all crawled (a full rotation), so
every day counts listings the same way; days older than ``DAILY_DAYS`` are kept weekly.

Values per category and area (``VALUE_FIELDS``):

- ``count``: listings on sale;
- ``n``, ``mean``, ``median``: those with a price; price in 万円 (lower bound of a range);
- ``unit_n``, ``unit_mean``, ``unit_median``: those with one price and one floor area
  (condo 専有面積, house 建物面積); 万円/m².

Price values are null when fewer than ``MIN_SAMPLE`` listings back them, so that no single
listing's price can be read off an area.
"""

from __future__ import annotations

import json
import shutil
import statistics
import tempfile
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from suumoviz import codec
from suumoviz.categories import CATEGORIES, PREFECTURE_AREA
from suumoviz.geocode import BOUNDARY_SOURCE, GEO_SOURCE, AreaCodes, Geocoder
from suumoviz.rotation import CYCLE_DAYS
from suumoviz.state import now_jst
from suumoviz.store import Row, listings_path, read_rows, runs_path

FORMAT_VERSION = 3
INDEX = "index.dat"
OUTPUTS = (INDEX, "day", "history", "summary.dat")  # summary.dat: format 2, removed
GRACE_DAYS = CYCLE_DAYS + 2
DAILY_DAYS = 90
MIN_SAMPLE = 3
MAX_FILE_BYTES = 4 * 1024 * 1024
VALUE_FIELDS = ["count", "n", "mean", "median", "unit_n", "unit_mean", "unit_median"]
PRICE_EVENTS = {"new", "price_change", "relisted"}

Values = list[Any]  # VALUE_FIELDS


class BuildError(Exception):
    pass


@dataclass
class BuildResult:
    out: Path
    files: int
    bytes: int
    dates: list[str]
    areas: dict[str, dict[str, int]]  # category → level → areas with listings, latest day
    listings: dict[str, int]  # category → listings on sale, latest day

    def summary(self) -> dict[str, Any]:
        return {
            "out": self.out.as_posix(),
            "files": self.files,
            "bytes": self.bytes,
            "dates": [self.dates[0], self.dates[-1], len(self.dates)],
            "areas": self.areas,
            "listings": self.listings,
        }


@dataclass
class _Listing:
    areas: tuple[str, ...]  # PREFECTURE_AREA, then the known area codes
    start: str  # first seen
    end: str  # first day no longer on sale
    price_days: list[str]  # ascending
    prices: list[tuple[str, str]]  # (price_min, price_max) from each price day on
    area_min: str
    area_max: str

    def price_on(self, day: str) -> tuple[str, str]:
        i = bisect_right(self.price_days, day) - 1
        return self.prices[max(i, 0)]


@dataclass
class _Group:
    count: int = 0
    prices: list[float] = field(default_factory=list)
    units: list[float] = field(default_factory=list)


def _days(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def timeline(runs: list[Row]) -> tuple[list[str], bool]:
    """Days of the timeline, and whether they follow a full rotation (else: latest only)."""
    merged = sorted(r["date"] for r in runs if r["merged"] == "true")
    if not merged:
        return [], False
    completed = {r["date"] for r in runs if r["merged"] == "true" and r["status"] == "completed"}
    first = next(
        (
            day
            for day in sorted(completed)
            if all(_days(day, i) in completed for i in range(CYCLE_DAYS))
        ),
        None,
    )
    start = _days(first, GRACE_DAYS - 1) if first else None
    if start is None or start > merged[-1]:
        return merged[-1:], False
    weekly_before = _days(merged[-1], -DAILY_DAYS)
    days = [
        day
        for day in merged
        if day >= start
        and (
            day > weekly_before
            or (date.fromisoformat(day) - date.fromisoformat(start)).days % 7 == 0
        )
    ]
    return days, True


def _price_events(data_dir: Path) -> dict[tuple[str, str], list[Row]]:
    events: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for path in sorted((data_dir / "events").glob("*.csv")):
        for row in read_rows(path):
            if row["type"] in PRICE_EVENTS:
                events[(row["category"], row["listing_id"])].append(row)
    return events


def _listings(
    data_dir: Path, category: str, geocoder: Geocoder, events: dict[tuple[str, str], list[Row]]
) -> list[_Listing]:
    rows = read_rows(listings_path(data_dir, category))
    for path in sorted((data_dir / "archive").glob("*.csv")):
        rows += [r for r in read_rows(path) if r["category"] == category]
    located: dict[tuple[str, str], AreaCodes] = {}
    result = []
    for row in rows:
        key = (row["address"], row["area_code"])
        if key not in located:
            place = geocoder.locate(row["address"], row["area_code"])
            located[key] = geocoder.area_codes(place) if place else (None, None, None)
        history = sorted(events.get((category, row["listing_id"]), []), key=lambda e: e["date"])
        if not history:
            history = [{"date": row["first_seen"], **row}]
        result.append(
            _Listing(
                areas=(PREFECTURE_AREA, *(c for c in located[key] if c)),
                start=row["first_seen"],
                end=_days(row["last_seen"], GRACE_DAYS),
                price_days=[e["date"] for e in history],
                prices=[(e["price_min"], e["price_max"]) for e in history],
                area_min=row["area_min"],
                area_max=row["area_max"],
            )
        )
    return result


def _single(low: str, high: str) -> bool:
    return not high or high == low


def _groups(listings: list[_Listing], day: str) -> dict[str, _Group]:
    groups: dict[str, _Group] = defaultdict(_Group)
    for item in listings:
        if not item.start <= day < item.end:
            continue
        price_min, price_max = item.price_on(day)
        price = float(price_min) if price_min else None
        size = float(item.area_min) if item.area_min else 0.0
        unit = (
            price / size
            if price
            and size > 0
            and _single(price_min, price_max)
            and _single(item.area_min, item.area_max)
            else None
        )
        for code in item.areas:
            group = groups[code]
            group.count += 1
            if price:
                group.prices.append(price)
            if unit:
                group.units.append(unit)
    return groups


def _values(group: _Group) -> Values:
    prices, units = group.prices, group.units
    priced = len(prices) >= MIN_SAMPLE
    unit_priced = len(units) >= MIN_SAMPLE
    return [
        group.count,
        len(prices),
        round(statistics.fmean(prices) / 10_000) if priced else None,
        round(statistics.median(prices) / 10_000) if priced else None,
        len(units),
        round(statistics.fmean(units) / 10_000, 1) if unit_priced else None,
        round(statistics.median(units) / 10_000, 1) if unit_priced else None,
    ]


def _parent(code: str) -> str:
    return {5: PREFECTURE_AREA, 9: code[:5], 11: code[:9]}[len(code)]


def _level(code: str) -> str:
    return {5: "city", 9: "town", 11: "chome"}[len(code)]


class _Writer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = 0
        self.bytes = 0

    def write(self, relative: str, payload: dict[str, Any]) -> None:
        body = codec.encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if len(body) > MAX_FILE_BYTES:
            raise BuildError(f"{relative} is {len(body)} bytes, over {MAX_FILE_BYTES}")
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.files += 1
        self.bytes += len(body)


def _official_counts(data_dir: Path) -> dict[tuple[str, str], int]:
    """(category, day) → listings on sale per SUUMO's city pages, all of Tokyo."""
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for path in sorted((data_dir / "counts").glob("*.csv")):
        for row in read_rows(path):
            totals[(row["category"], row["date"])] += int(row["count"])
    return dict(totals)


def _category(
    writer: _Writer, key: str, listings: list[_Listing], days: list[str]
) -> tuple[list[Values | None], dict[str, int]]:
    """Writes the day and history files of one category; returns the Tokyo series and
    the number of areas per level on the latest day."""
    series: dict[str, list[Values | None]] = {}
    for i, day in enumerate(days):
        groups = _groups(listings, day)
        rows = []
        for code in sorted(groups):
            values = _values(groups[code])
            series.setdefault(code, [None] * len(days))[i] = values
            if code != PREFECTURE_AREA:
                rows.append([code, *values])
        writer.write(
            f"day/{day}/{key}.dat",
            {"date": day, "category": key, "fields": ["code", *VALUE_FIELDS], "rows": rows},
        )
    tokyo = series.pop(PREFECTURE_AREA, [None] * len(days))
    by_parent: dict[str, dict[str, list[Values | None]]] = defaultdict(dict)
    for code in sorted(series):
        by_parent[_parent(code)][code] = series[code]
    for parent, children in sorted(by_parent.items()):
        writer.write(
            f"history/{key}/{parent}.dat",
            {
                "category": key,
                "parent": parent,
                "dates": days,
                "fields": VALUE_FIELDS,
                "series": children,
            },
        )
    levels = {"city": 0, "town": 0, "chome": 0}
    for code, values in series.items():
        if values[-1] is not None:
            levels[_level(code)] += 1
    return tokyo, levels


def build_site(
    data_dir: Path,
    out_dir: Path,
    *,
    geocoder: Geocoder | None = None,
    now: datetime | None = None,
) -> BuildResult:
    runs = read_rows(runs_path(data_dir))
    days, complete = timeline(runs)
    if not days:
        raise BuildError(f"no merged run in {runs_path(data_dir)}")
    merged = sorted(r["date"] for r in runs if r["merged"] == "true")
    geocoder = geocoder or Geocoder.load()
    events = _price_events(data_dir)
    official = _official_counts(data_dir)

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-", dir=out_dir.parent))
    try:
        writer = _Writer(staging)
        categories = []
        areas: dict[str, dict[str, int]] = {}
        on_sale: dict[str, int] = {}
        for key, category in CATEGORIES.items():
            listings = _listings(data_dir, key, geocoder, events)
            tokyo, areas[key] = _category(writer, key, listings, days)
            on_sale[key] = tokyo[-1][0] if tokyo[-1] else 0
            categories.append(
                {
                    "key": key,
                    "label": category.label,
                    "tokyo": tokyo,
                    "official": [official.get((key, day)) for day in days],
                }
            )
        writer.write(
            INDEX,
            {
                "version": FORMAT_VERSION,
                "generated_at": (now or now_jst()).isoformat(timespec="seconds"),
                "first_date": merged[0],
                "latest_date": merged[-1],
                "complete": complete,
                "dates": days,
                "grace_days": GRACE_DAYS,
                "min_sample": MIN_SAMPLE,
                "units": {"price": "万円", "unit": "万円/m²"},
                "sources": {
                    "listings": "SUUMO 列表页（按区域汇总）",
                    "geo": GEO_SOURCE,
                    "boundaries": BOUNDARY_SOURCE,
                },
                "fields": VALUE_FIELDS,
                "categories": categories,
            },
        )
        for name in OUTPUTS:
            old = out_dir / name
            if old.is_dir():
                shutil.rmtree(old)
            elif old.exists():
                old.unlink()
        out_dir.mkdir(exist_ok=True)
        for item in staging.iterdir():
            item.replace(out_dir / item.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return BuildResult(out_dir, writer.files, writer.bytes, days, areas, on_sale)

"""Web data: average prices per SUUMO area, built from the data tables.

Writes one file, ``{out}/summary.dat``: a JSON document obfuscated with ``codec`` (the
page decodes it in the browser). Only per-area aggregates are published, never single
listings::

    {
      "version": 2,
      "generated_at": "2026-11-19T08:00:00+09:00",
      "first_date": "2026-11-07",          # first and latest merged days
      "latest_date": "2026-11-18",
      "units": {"price": "万円", "unit": "万円/m²"},
      "sources": {"listings": "...", "geo": "..."},
      "areas": {"fields": ["code", "name", "lat", "lng"], "rows": [...]},
      "categories": [
        {"key": "used_condo", "label": "中古マンション",
         "fields": ["area", "count", "n", "mean", "median", "unit_mean"],
         "rows": [["13000", 37109, 36240, 7012, 5480, 112.3], ...]}
      ]
    }

Per category and area (``13000`` = all of Tokyo):

- ``count``: listings on sale on the latest day of the city pages (exact);
- ``n``: active listings with a price in the tables (the census, refreshed every 7 days);
- ``mean`` / ``median``: their price in 万円 (lower bound of a price range);
- ``unit_mean``: mean price per m² in 万円/m² (condo: 専有面積, house: 建物面積; land-only
  listings and 新築マンション are left out, as in the stats table).
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from suumoviz import codec
from suumoviz.categories import CATEGORIES, PREFECTURE_AREA
from suumoviz.geocode import GEO_SOURCE, Geocoder
from suumoviz.state import now_jst
from suumoviz.store import Row, listings_path, read_rows, runs_path

FORMAT_VERSION = 2
OUTPUT = "summary.dat"
MAX_FILE_BYTES = 1024 * 1024
PREFECTURE_NAME = "東京都"
ISLANDS_FROM = "13360"  # municipality codes of the 伊豆・小笠原 islands start here
AREA_COLUMNS = ["code", "name", "lat", "lng"]
VALUE_COLUMNS = ["area", "count", "n", "mean", "median", "unit_mean"]
NO_UNIT_PRICE = {"new_condo"}  # a price range over units of different sizes


class BuildError(Exception):
    pass


@dataclass
class BuildResult:
    path: Path
    bytes: int
    areas: dict[str, int]  # category → areas with values
    listings: dict[str, int]  # category → listings with a price (prefecture-wide n)

    def summary(self) -> dict[str, Any]:
        return {
            "file": self.path.as_posix(),
            "bytes": self.bytes,
            "areas": self.areas,
            "listings": self.listings,
        }


def _read_all(data_dir: Path, folder: str) -> list[Row]:
    return [row for path in sorted((data_dir / folder).glob("*.csv")) for row in read_rows(path)]


def _man(yen: float) -> int:
    return round(yen / 10_000)


def _latest_counts(counts: list[Row]) -> dict[str, dict[str, int]]:
    """category → area → count on that category's latest day (13000 = sum)."""
    latest: dict[str, str] = {}
    for row in counts:
        latest[row["category"]] = max(latest.get(row["category"], ""), row["date"])
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for row in counts:
        if row["date"] == latest[row["category"]]:
            by_area = result[row["category"]]
            by_area[row["area_code"]] = int(row["count"])
            by_area[PREFECTURE_AREA] = by_area.get(PREFECTURE_AREA, 0) + int(row["count"])
    return result


def _prices(category: str, rows: list[Row]) -> dict[str, tuple[list[float], list[float]]]:
    """area → (prices, unit prices) of active listings, in yen and yen/m²."""
    groups: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for row in rows:
        if row["status"] != "active" or not row["price_min"]:
            continue
        price = float(row["price_min"])
        size = float(row["area_min"]) if row["area_min"] else 0.0
        for area in (row["area_code"], PREFECTURE_AREA):
            prices, units = groups[area]
            prices.append(price)
            if category not in NO_UNIT_PRICE and size > 0:
                units.append(price / size)
    return groups


def _category(category: str, counts: dict[str, int], data_dir: Path) -> list[list[Any]]:
    prices = _prices(category, read_rows(listings_path(data_dir, category)))
    rows: list[list[Any]] = []
    for area in sorted(set(counts) | set(prices)):
        values, units = prices.get(area, ([], []))
        count = counts.get(area)
        if not values and not count:
            continue
        rows.append(
            [
                area,
                count,
                len(values),
                _man(statistics.fmean(values)) if values else None,
                _man(statistics.median(values)) if values else None,
                round(statistics.fmean(units) / 10_000, 1) if units else None,
            ]
        )
    return rows


def _areas(counts: list[Row], geocoder: Geocoder) -> dict[str, Any]:
    names: dict[str, str] = {}
    for row in sorted(counts, key=lambda r: r["date"]):
        names[row["area_code"]] = row["area_name"]  # latest name wins
    # mainland only: the islands (13360+) would pull the point into the sea
    mainland = [p for code, p in geocoder.cities.items() if code < ISLANDS_FROM]
    rows: list[list[Any]] = [
        [
            PREFECTURE_AREA,
            PREFECTURE_NAME,
            round(statistics.fmean(p.lat for p in mainland), 6) if mainland else None,
            round(statistics.fmean(p.lng for p in mainland), 6) if mainland else None,
        ]
    ]
    for code in sorted(names):
        point = geocoder.area_point(code, names[code])
        rows.append([code, names[code], point.lat if point else None, point.lng if point else None])
    return {"fields": AREA_COLUMNS, "rows": rows}


def build_site(
    data_dir: Path,
    out_dir: Path,
    *,
    geocoder: Geocoder | None = None,
    now: datetime | None = None,
) -> BuildResult:
    runs = read_rows(runs_path(data_dir))
    merged = sorted(r["date"] for r in runs if r["merged"] == "true")
    if not merged:
        raise BuildError(f"no merged run in {runs_path(data_dir)}")
    geocoder = geocoder or Geocoder.load()
    counts = _read_all(data_dir, "counts")
    latest = _latest_counts(counts)

    categories = []
    for key, category in CATEGORIES.items():
        rows = _category(key, latest.get(key, {}), data_dir)
        categories.append(
            {"key": key, "label": category.label, "fields": VALUE_COLUMNS, "rows": rows}
        )
    payload = {
        "version": FORMAT_VERSION,
        "generated_at": (now or now_jst()).isoformat(timespec="seconds"),
        "first_date": merged[0],
        "latest_date": merged[-1],
        "units": {"price": "万円", "unit": "万円/m²"},
        "sources": {"listings": "SUUMO 列表页（按区域汇总）", "geo": GEO_SOURCE},
        "areas": _areas(counts, geocoder),
        "categories": categories,
    }
    body = codec.encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if len(body) > MAX_FILE_BYTES:
        raise BuildError(f"{OUTPUT} is {len(body)} bytes, over {MAX_FILE_BYTES}")
    path = out_dir / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)

    def prefecture_n(c: dict[str, Any]) -> int:
        return next((r[2] for r in c["rows"] if r[0] == PREFECTURE_AREA), 0)

    return BuildResult(
        path=path,
        bytes=len(body),
        areas={c["key"]: sum(1 for r in c["rows"] if r[0] != PREFECTURE_AREA) for c in categories},
        listings={c["key"]: prefecture_n(c) for c in categories},
    )

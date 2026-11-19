"""CSV tables under the data directory (committed to the ``data`` branch).

All tables are UTF-8 CSV with a header row, written atomically and in a stable
order so that day-to-day git diffs stay small. On disk every table is obfuscated
line by line (see ``codec``); readers also accept plain CSV.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from pathlib import Path

from suumoviz import codec

Row = dict[str, str]

# Listing attributes copied from the day snapshot (see models.Listing).
LISTING_DATA_FIELDS = [
    "listing_id",
    "category",
    "area_code",
    "name",
    "price_min",
    "price_max",
    "price_raw",
    "address",
    "line",
    "station",
    "walk_min",
    "access_raw",
    "area_min",
    "area_max",
    "land_min",
    "land_max",
    "layout",
    "balcony",
    "built_ym",
    "delivery_raw",
    "path",  # detail page path; new_house pages also list land under /tochi/
]
LISTING_FIELDS = [
    *LISTING_DATA_FIELDS,
    "first_seen",
    "last_seen",
    "last_price_change",
    "status",  # active | inactive
    "delisted_on",
]
EVENT_FIELDS = [
    "date",
    "category",
    "area_code",
    "listing_id",
    "type",  # new | price_change | delisted | relisted
    "price_min_old",
    "price_max_old",
    "price_min",
    "price_max",
]
# What history needs of a listing pruned from listings/ (prices come from the events).
ARCHIVE_FIELDS = [
    "listing_id",
    "category",
    "area_code",
    "address",
    "price_min",
    "price_max",
    "area_min",
    "area_max",
    "first_seen",
    "last_seen",
    "delisted_on",
]
COUNT_FIELDS = ["date", "category", "area_code", "area_name", "count"]
STAT_FIELDS = [
    "date",
    "scope",  # sample: pages fetched that day | census: all active listings
    "category",
    "area_code",
    "n",
    "price_p25",
    "price_median",
    "price_p75",
    "unit_n",
    "unit_price_median",  # yen per m2 (condo: 専有面積, house: 建物面積)
]
RUN_FIELDS = [
    "date",
    "slot",
    "status",
    "stop_reason",
    "requests",
    "planned_pages",
    "fetched_pages",
    "failed_pages",
    "listings",
    "merged",
    "quality",
    "new",
    "price_changes",
    "delisted",
    "relisted",
]


def read_rows(path: Path) -> list[Row]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(codec.read_text(path), newline="")))


def write_rows(path: Path, fields: list[str], rows: Iterable[Row]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({f: row.get(f, "") for f in fields})
    codec.write_text(path, buffer.getvalue())


def replace_day(path: Path, fields: list[str], day: str, rows: list[Row]) -> None:
    """Upsert: drop existing rows for ``day`` and append ``rows`` (sorted by date)."""
    kept = [r for r in read_rows(path) if r["date"] != day]
    merged = sorted([*kept, *rows], key=lambda r: r["date"])  # stable within a day
    write_rows(path, fields, merged)


def listings_path(data_dir: Path, category: str) -> Path:
    return data_dir / "listings" / f"{category}.csv"


def events_path(data_dir: Path, day: str) -> Path:
    return data_dir / "events" / f"{day[:7]}.csv"


def archive_path(data_dir: Path, day: str) -> Path:
    """Listings pruned on ``day``."""
    return data_dir / "archive" / f"{day[:4]}.csv"


def counts_path(data_dir: Path, day: str) -> Path:
    return data_dir / "counts" / f"{day[:4]}.csv"


def stats_path(data_dir: Path, day: str) -> Path:
    return data_dir / "stats" / f"{day[:4]}.csv"


def runs_path(data_dir: Path) -> Path:
    return data_dir / "runs.csv"

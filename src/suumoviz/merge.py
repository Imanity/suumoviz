"""Merge a day snapshot (work/{date}/) into the persistent tables (data/).

Re-merging the same day is a no-op; merging a day older than the latest merged
day is refused. Only pages fetched successfully are merged, and only when the
snapshot passes the quality gate.
"""

from __future__ import annotations

import json
import statistics
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from suumoviz.categories import CATEGORIES, PREFECTURE_AREA
from suumoviz.quality import Quality, check_quality
from suumoviz.rotation import CYCLE_DAYS
from suumoviz.store import (
    ARCHIVE_FIELDS,
    COUNT_FIELDS,
    EVENT_FIELDS,
    LISTING_DATA_FIELDS,
    LISTING_FIELDS,
    RUN_FIELDS,
    STAT_FIELDS,
    Row,
    archive_path,
    counts_path,
    events_path,
    listings_path,
    read_rows,
    replace_day,
    runs_path,
    stats_path,
    write_rows,
)

DELIST_AFTER_DAYS = 2 * CYCLE_DAYS + 1  # missed two full cycles
MIN_COMPLETED_RUNS = 2 * CYCLE_DAYS - 1  # completed runs needed in that window
INACTIVE_RETENTION_DAYS = 90  # delisted rows move from listings/ to archive/ after this


class MergeError(Exception):
    pass


@dataclass
class MergeResult:
    day: str
    merged: bool
    quality: Quality
    events: dict[str, int] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 0 if self.merged else 1


@dataclass
class Snapshot:
    run: dict[str, object]
    pages: list[Row]
    listings: list[Row]
    counts: list[Row]

    @classmethod
    def load(cls, directory: Path) -> Snapshot:
        run_file = directory / "run.json"
        if not run_file.exists():
            raise MergeError(f"no run.json in {directory}")
        return cls(
            run=json.loads(run_file.read_text(encoding="utf-8")),
            pages=read_rows(directory / "pages.csv"),
            listings=read_rows(directory / "listings.csv"),
            counts=read_rows(directory / "counts.csv"),
        )


def _key(row: Row) -> tuple[str, str]:
    return row["category"], row["listing_id"]


def _load_listings(data_dir: Path) -> dict[tuple[str, str], Row]:
    table: dict[tuple[str, str], Row] = {}
    for category in CATEGORIES:
        for row in read_rows(listings_path(data_dir, category)):
            table[_key(row)] = row
    return table


def _save_listings(data_dir: Path, table: dict[tuple[str, str], Row]) -> None:
    for category in CATEGORIES:
        rows = sorted(
            (r for (cat, _), r in table.items() if cat == category),
            key=lambda r: r["listing_id"],
        )
        if rows or listings_path(data_dir, category).exists():
            write_rows(listings_path(data_dir, category), LISTING_FIELDS, rows)


def _event(day: str, row: Row, kind: str, old: Row | None = None) -> Row:
    return {
        "date": day,
        "category": row["category"],
        "area_code": row["area_code"],
        "listing_id": row["listing_id"],
        "type": kind,
        "price_min_old": old["price_min"] if old else "",
        "price_max_old": old["price_max"] if old else "",
        "price_min": row["price_min"] if kind != "delisted" else "",
        "price_max": row["price_max"] if kind != "delisted" else "",
    }


def _apply_sightings(
    table: dict[tuple[str, str], Row], sightings: list[Row], day: str
) -> list[Row]:
    events: list[Row] = []
    for seen in sightings:
        data = {f: seen.get(f, "") for f in LISTING_DATA_FIELDS}
        current = table.get(_key(seen))
        if current is None:
            table[_key(seen)] = {
                **data,
                "first_seen": day,
                "last_seen": day,
                "last_price_change": "",
                "status": "active",
                "delisted_on": "",
            }
            events.append(_event(day, data, "new"))
            continue
        if current["status"] == "inactive":
            events.append(_event(day, data, "relisted"))
            current["status"], current["delisted_on"] = "active", ""
        if (current["price_min"], current["price_max"]) != (data["price_min"], data["price_max"]):
            events.append(_event(day, data, "price_change", old=current))
            current["last_price_change"] = day
        current.update(data)
        current["last_seen"] = max(current["last_seen"], day)
    return events


def _delist(table: dict[tuple[str, str], Row], runs: list[Row], day: str) -> list[Row]:
    completed = sorted(
        r["date"] for r in runs if r["status"] == "completed" and r["merged"] == "true"
    )
    today = date.fromisoformat(day)
    events: list[Row] = []
    for row in table.values():
        if row["status"] != "active":
            continue
        last = date.fromisoformat(row["last_seen"])
        if (today - last).days < DELIST_AFTER_DAYS:
            continue
        runs_since = bisect_right(completed, day) - bisect_right(completed, row["last_seen"])
        if runs_since >= MIN_COMPLETED_RUNS:
            row["status"], row["delisted_on"] = "inactive", day
            events.append(_event(day, row, "delisted", old=row))
    return events


def _prune(table: dict[tuple[str, str], Row], day: str) -> list[Row]:
    """Remove long-delisted rows from ``table`` and return them (for archive/)."""
    cutoff = (date.fromisoformat(day) - timedelta(days=INACTIVE_RETENTION_DAYS)).isoformat()
    keys = [k for k, r in table.items() if r["status"] == "inactive" and r["delisted_on"] < cutoff]
    return [table.pop(k) for k in sorted(keys)]


def _archive(data_dir: Path, day: str, pruned: list[Row]) -> None:
    if not pruned:
        return
    path = archive_path(data_dir, day)
    existing = read_rows(path)
    seen = {(r["category"], r["listing_id"], r["delisted_on"]) for r in existing}
    fresh = [r for r in pruned if (r["category"], r["listing_id"], r["delisted_on"]) not in seen]
    write_rows(path, ARCHIVE_FIELDS, existing + fresh)


def _quartiles(values: list[float]) -> tuple[int, int, int]:
    if len(values) == 1:
        v = round(values[0])
        return v, v, v
    q1, q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return round(q1), round(q2), round(q3)


def _stats(day: str, scope: str, rows: list[Row]) -> list[Row]:
    """Per (category, area) plus a prefecture-wide row per category (PREFECTURE_AREA)."""
    groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in rows:
        groups[(row["category"], row["area_code"])].append(row)
        groups[(row["category"], PREFECTURE_AREA)].append(row)
    out: list[Row] = []
    for (category, area_code), group in sorted(groups.items()):
        prices = [float(r["price_min"]) for r in group if r["price_min"]]
        units = (
            [
                float(r["price_min"]) / float(r["area_min"])
                for r in group
                if r["price_min"] and r["area_min"] and float(r["area_min"]) > 0
            ]
            if category != "new_condo"
            else []
        )
        p25, p50, p75 = _quartiles(prices) if prices else ("", "", "")
        out.append(
            {
                "date": day,
                "scope": scope,
                "category": category,
                "area_code": area_code,
                "n": str(len(group)),
                "price_p25": str(p25),
                "price_median": str(p50),
                "price_p75": str(p75),
                "unit_n": str(len(units)),
                "unit_price_median": str(round(statistics.median(units))) if units else "",
            }
        )
    return out


def merge_day(data_dir: Path, snapshot_dir: Path) -> MergeResult:
    snapshot = Snapshot.load(snapshot_dir)
    day = str(snapshot.run["date"])
    runs = read_rows(runs_path(data_dir))
    latest = max((r["date"] for r in runs if r["merged"] == "true"), default="")
    if latest > day:
        raise MergeError(f"{day} is older than the latest merged day {latest}")

    # one row per listing; a listing seen on two pages (boundary shift) keeps the last sighting
    sightings = list({_key(r): r for r in snapshot.listings}.values())
    quality = check_quality(snapshot.pages, sightings)

    run_row: Row = {
        f: "" if snapshot.run.get(f) is None else str(snapshot.run[f]) for f in RUN_FIELDS
    }
    run_row["merged"] = "true" if quality.ok else "false"
    run_row["quality"] = quality.summary()
    runs = [r for r in runs if r["date"] != day] + [run_row]

    table = _load_listings(data_dir)
    if quality.ok:
        events = _apply_sightings(table, sightings, day)
        events += _delist(table, runs, day)
        _archive(data_dir, day, _prune(table, day))
        _save_listings(data_dir, table)
        existing = read_rows(events_path(data_dir, day))
        seen = {(e["date"], e["listing_id"], e["type"]) for e in existing}
        fresh = [e for e in events if (e["date"], e["listing_id"], e["type"]) not in seen]
        write_rows(events_path(data_dir, day), EVENT_FIELDS, existing + fresh)
        census = [r for r in table.values() if r["status"] == "active"]
        stats = _stats(day, "sample", sightings) + _stats(day, "census", census)
        replace_day(stats_path(data_dir, day), STAT_FIELDS, day, stats)

    if snapshot.counts:
        replace_day(counts_path(data_dir, day), COUNT_FIELDS, day, snapshot.counts)

    day_events = [e for e in read_rows(events_path(data_dir, day)) if e["date"] == day]
    counts = {kind: 0 for kind in ("new", "price_change", "delisted", "relisted")}
    for e in day_events:
        counts[e["type"]] += 1
    run_row.update(
        new=str(counts["new"]),
        price_changes=str(counts["price_change"]),
        delisted=str(counts["delisted"]),
        relisted=str(counts["relisted"]),
    )
    write_rows(runs_path(data_dir), RUN_FIELDS, sorted(runs, key=lambda r: r["date"]))
    return MergeResult(day, quality.ok, quality, counts)

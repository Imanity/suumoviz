"""One daily crawl: robots check → city pages → today's rotation slot → list pages.

Writes a day snapshot to ``{work_dir}/{date}/`` (counts, pages, listings, run summary)
and updates ``{data_dir}/state.json``. Never logs listing contents.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

from suumoviz import codec
from suumoviz.categories import BASE_URL, CATEGORIES
from suumoviz.fetch import Blocked, BudgetExceeded, CrawlError, Fetcher, PageError
from suumoviz.models import Area, Listing
from suumoviz.parse import parse_city_page, parse_list_page
from suumoviz.robots import Robots
from suumoviz.rotation import (
    CYCLE_DAYS,
    PageTask,
    assign_offsets,
    build_combos,
    daily_load,
    plan_day,
    slot_for,
)
from suumoviz.state import STATE_FILE, State, now_jst

ROBOTS_URL = f"{BASE_URL}/robots.txt"
ROBOTS_PRODUCT = "SuumoViz"
CONSECUTIVE_FAILURE_LIMIT = 3

EXIT_OK, EXIT_PARTIAL, EXIT_BLOCKED = 0, 1, 2
_EXIT = {
    "completed": EXIT_OK,
    "limited": EXIT_OK,
    "planned": EXIT_OK,
    "skipped": EXIT_OK,
    "partial": EXIT_PARTIAL,
    "failed": EXIT_PARTIAL,
    "blocked": EXIT_BLOCKED,
}


class LayoutChanged(CrawlError):
    """A page no longer matches the known structure."""


@dataclass
class CrawlOptions:
    day: date
    data_dir: Path
    work_dir: Path
    dry_run: bool = False
    max_pages: int | None = None
    city_html_dir: Path | None = None
    categories: tuple[str, ...] = tuple(CATEGORIES)


@dataclass
class PageRecord:
    category: str
    area_code: str
    page: int
    pages: int
    url: str
    status: str  # ok | error | blocked
    error: str = ""
    expected_total: int = 0
    total: int | None = None
    items: int = 0
    fetched_at: str = ""


@dataclass
class CrawlResult:
    status: str
    stop_reason: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return _EXIT[self.status]


class _Run:
    def __init__(self, options: CrawlOptions, fetcher: Fetcher | None, now, log) -> None:
        self.options = options
        self.fetcher = fetcher
        self.now: Callable[[], datetime] = now
        self.log: Callable[[str], None] = log
        self.state_path = options.data_dir / STATE_FILE
        self.state = State.load(self.state_path)
        self.started = now()
        self.areas: dict[str, list[Area]] = {}
        self.pages: list[PageRecord] = []
        self.listings: list[tuple[PageTask, Listing]] = []
        self.robots_sha256: str | None = None

    # -- inputs ---------------------------------------------------------------------

    def _need_fetcher(self) -> Fetcher:
        if self.fetcher is None:
            raise RuntimeError("network access requires a Fetcher")
        return self.fetcher

    def load_areas(self) -> Robots | None:
        if self.options.city_html_dir is not None:
            for key in self.options.categories:
                path = self.options.city_html_dir / f"city_{key}.html"
                self.areas[key] = parse_city_page(codec.read_bytes(path), CATEGORIES[key])
            return None

        fetcher = self._need_fetcher()
        response = fetcher.get(ROBOTS_URL)
        robots = Robots(response.text(), ROBOTS_PRODUCT)
        self.robots_sha256 = hashlib.sha256(response.body).hexdigest()
        if self.state.robots_sha256 and self.robots_sha256 != self.state.robots_sha256:
            self.log("notice: robots.txt changed since the last run; re-checking all URLs")
        for key in self.options.categories:
            url = CATEGORIES[key].city_url()
            if not robots.allowed(url):
                raise Blocked("robots_disallow")
            areas = parse_city_page(fetcher.get(url).body, CATEGORIES[key])
            if not any(area.count for area in areas):
                raise LayoutChanged(f"city_page_layout:{key}")
            self.areas[key] = areas
        return robots

    # -- list pages -----------------------------------------------------------------

    def fetch_pages(self, tasks: list[PageTask]) -> tuple[str, str | None]:
        fetcher = self._need_fetcher()
        failures = 0
        for index, task in enumerate(tasks, 1):
            record = PageRecord(
                category=task.category,
                area_code=task.area_code,
                page=task.page,
                pages=task.pages,
                url=task.url,
                status="ok",
                expected_total=task.expected_total,
                fetched_at=self.now().isoformat(timespec="seconds"),
            )
            self.pages.append(record)
            prefix = f"[{index}/{len(tasks)}] {task.category} {task.area_code} p{task.page}"
            try:
                response = fetcher.get(task.url)
            except Blocked as exc:
                record.status, record.error = "blocked", exc.reason
                self.log(f"{prefix}: blocked ({exc.reason})")
                raise
            except BudgetExceeded as exc:
                self.pages.pop()
                self.log(f"stop: {exc.reason}")
                return "partial", exc.reason
            except PageError as exc:
                record.status, record.error = "error", exc.reason
                self.log(f"{prefix}: error ({exc.reason})")
                failures += 1
                if failures >= CONSECUTIVE_FAILURE_LIMIT:
                    return "partial", "consecutive_page_failures"
                continue

            page = parse_list_page(response.body, CATEGORIES[task.category])
            record.total, record.items = page.total, len(page.listings)
            if page.total is None and not page.listings:
                record.status, record.error = "error", "unknown_layout"
                self.log(f"{prefix}: unrecognized page layout")
                failures += 1
                if failures >= CONSECUTIVE_FAILURE_LIMIT:
                    return "partial", "unknown_layout"
                continue
            failures = 0
            self.listings.extend((task, listing) for listing in page.listings)
            self.log(f"{prefix}/{task.pages}: {len(page.listings)} items")
        if any(p.status != "ok" for p in self.pages):
            return "partial", "page_errors"
        return "completed", None

    # -- outputs --------------------------------------------------------------------

    def summary(self, status: str, stop_reason: str | None, planned: int) -> dict[str, Any]:
        finished = self.now()
        return {
            "date": self.options.day.isoformat(),
            "slot": slot_for(self.options.day),
            "status": status,
            "stop_reason": stop_reason,
            "started_at": self.started.isoformat(timespec="seconds"),
            "finished_at": finished.isoformat(timespec="seconds"),
            "requests": self.fetcher.requests if self.fetcher else 0,
            "planned_pages": planned,
            "fetched_pages": sum(1 for p in self.pages if p.status == "ok"),
            "failed_pages": sum(1 for p in self.pages if p.status != "ok"),
            "listings": len(self.listings),
            "robots_sha256": self.robots_sha256,
        }

    def write_snapshot(self, summary: dict[str, Any]) -> Path:
        out = self.options.work_dir / self.options.day.isoformat()
        out.mkdir(parents=True, exist_ok=True)
        day = self.options.day.isoformat()
        _write_csv(
            out / "counts.csv",
            ["date", "category", "area_code", "area_name", "slug", "count"],
            (
                [day, key, a.code, a.name, a.slug or "", a.count]
                for key, areas in self.areas.items()
                for a in areas
            ),
        )
        page_fields = [f.name for f in fields(PageRecord)]
        _write_csv(
            out / "pages.csv",
            ["date", *page_fields],
            ([day, *asdict(p).values()] for p in self.pages),
        )
        listing_fields = [f.name for f in fields(Listing)]
        _write_csv(
            out / "listings.csv",
            ["date", "area_code", "page", *listing_fields],
            (
                [day, task.area_code, task.page, *_listing_values(listing)]
                for task, listing in self.listings
            ),
        )
        (out / "run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return out

    def save_state(self, offsets: dict[str, int] | None, summary: dict[str, Any]) -> None:
        if offsets is not None:
            self.state.offsets = offsets
        if self.robots_sha256:
            self.state.robots_sha256 = self.robots_sha256
        self.state.last_run = {
            k: summary[k] for k in ("date", "status", "stop_reason", "requests", "listings")
        }
        self.state.save(self.state_path)


def _listing_values(listing: Listing) -> list[Any]:
    values = asdict(listing)
    values["labels"] = "|".join(listing.labels)
    return ["" if v is None else v for v in values.values()]


def _write_csv(path: Path, header: list[str], rows: Iterable[Iterable[Any]]) -> None:
    """Snapshot tables are obfuscated like the data tables (they are uploaded as artifacts)."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    codec.write_text(path, buffer.getvalue())


def describe_plan(
    day: date, tasks: list[PageTask], load: list[int], combos: int, total_pages: int
) -> list[str]:
    per_category = Counter(t.category for t in tasks)
    lines = [
        f"date {day.isoformat()} (JST)  slot {slot_for(day)} of {CYCLE_DAYS}",
        f"combos with listings: {combos}  pages in full cycle: {total_pages}",
        f"pages per slot: {load}",
        f"today: {len(tasks)} list pages + 5 robots/city requests = {len(tasks) + 5} requests",
        "by category: " + ", ".join(f"{k} {v}" for k, v in sorted(per_category.items())),
    ]
    lines += [
        f"  {t.category:<10} {t.area_code} {t.area_name:<6} p{t.page}/{t.pages}  {t.url}"
        for t in tasks
    ]
    return lines


def run_crawl(
    options: CrawlOptions,
    fetcher: Fetcher | None,
    *,
    now: Callable[[], datetime] = now_jst,
    log: Callable[[str], None] = print,
) -> CrawlResult:
    run = _Run(options, fetcher, now, log)

    if not options.dry_run and run.state.in_cooldown(run.started):
        log(f"skip: cooling down until {run.state.cooldown_until} ({run.state.cooldown_reason})")
        return CrawlResult("skipped", "cooldown")

    def stop(status: str, reason: str, planned: int, offsets: dict[str, int] | None) -> CrawlResult:
        summary = run.summary(status, reason, planned)
        if not options.dry_run:
            run.write_snapshot(summary)
        if not options.dry_run or status == "blocked":  # a real block is kept even in dry runs
            run.save_state(offsets, summary)
        return CrawlResult(status, reason, summary)

    try:
        robots = run.load_areas()
    except Blocked as exc:
        until = run.state.start_cooldown(run.now(), exc.reason, exc.retry_after)
        log(f"blocked while planning ({exc.reason}); cooling down until {until}")
        return stop("blocked", exc.reason, 0, None)
    except CrawlError as exc:
        log(f"failed while planning ({exc.reason})")
        return stop("failed", exc.reason, 0, None)

    combos = build_combos(run.areas)
    offsets = assign_offsets(combos, run.state.offsets)
    tasks = plan_day(combos, offsets, options.day)
    if options.dry_run:
        load = daily_load(combos, offsets)
        for line in describe_plan(options.day, tasks, load, len(combos), sum(load)):
            log(line)
        return CrawlResult("planned", None, {"planned_pages": len(tasks), "load": load})

    if robots is not None and robots.disallowed([t.url for t in tasks]):
        until = run.state.start_cooldown(run.now(), "robots_disallow", None)
        log(f"robots.txt disallows planned URLs; cooling down until {until}")
        return stop("blocked", "robots_disallow", len(tasks), offsets)

    selected = tasks if options.max_pages is None else tasks[: options.max_pages]
    try:
        status, reason = run.fetch_pages(selected)
    except Blocked as exc:
        until = run.state.start_cooldown(run.now(), exc.reason, exc.retry_after)
        log(f"blocked ({exc.reason}); cooling down until {until}")
        return stop("blocked", exc.reason, len(tasks), offsets)
    if status == "completed" and len(selected) < len(tasks):
        status, reason = "limited", f"max_pages={options.max_pages}"
    summary = run.summary(status, reason, len(tasks))
    run.write_snapshot(summary)
    run.save_state(offsets, summary)
    log(
        json.dumps(
            {
                k: summary[k]
                for k in ("status", "requests", "fetched_pages", "failed_pages", "listings")
            }
        )
    )
    return CrawlResult(status, reason, summary)

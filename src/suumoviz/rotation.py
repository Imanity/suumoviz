"""7-day rotation: which list pages to fetch on a given day.

A *combo* is one (category, municipality). Its pages are ``ceil(count / 100)``.
Page ``i`` (1-based) is fetched on the day whose slot equals ``(i - 1 + offset) % 7``,
so every page is fetched exactly once per cycle. Offsets are persisted; a combo seen
for the first time gets the least-loaded offset, and existing offsets never move.
Categories without address sort (new condo) fetch all their pages on one day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from suumoviz.categories import CATEGORIES, PAGE_SIZE
from suumoviz.models import Area

CYCLE_DAYS = 7
EPOCH = date(2026, 11, 2)  # a Monday; slot 0


def slot_for(day: date) -> int:
    return (day - EPOCH).days % CYCLE_DAYS


def combo_key(category: str, area_code: str) -> str:
    return f"{category}:{area_code}"


@dataclass(frozen=True)
class Combo:
    category: str
    area: Area

    @property
    def key(self) -> str:
        return combo_key(self.category, self.area.code)

    @property
    def pages(self) -> int:
        return math.ceil(self.area.count / PAGE_SIZE)

    @property
    def same_day(self) -> bool:
        return not CATEGORIES[self.category].address_sort

    def slots(self, offset: int) -> list[int]:
        """Slot of each page, index 0 = page 1."""
        if self.same_day:
            return [offset % CYCLE_DAYS] * self.pages
        return [(i + offset) % CYCLE_DAYS for i in range(self.pages)]


@dataclass(frozen=True)
class PageTask:
    category: str
    area_code: str
    area_name: str
    slug: str
    page: int
    pages: int
    expected_total: int

    @property
    def url(self) -> str:
        return CATEGORIES[self.category].list_url(self.slug, self.page)


def build_combos(areas_by_category: dict[str, list[Area]]) -> list[Combo]:
    return [
        Combo(category, area)
        for category, areas in areas_by_category.items()
        for area in areas
        if area.count > 0 and area.slug
    ]


def daily_load(combos: list[Combo], offsets: dict[str, int]) -> list[int]:
    load = [0] * CYCLE_DAYS
    for combo in combos:
        if combo.key in offsets:
            for slot in combo.slots(offsets[combo.key]):
                load[slot] += 1
    return load


def assign_offsets(combos: list[Combo], offsets: dict[str, int]) -> dict[str, int]:
    """Return offsets with every combo assigned; existing entries are kept unchanged."""
    result = dict(offsets)
    load = daily_load(combos, result)
    new = sorted((c for c in combos if c.key not in result), key=lambda c: (-c.pages, c.key))
    for combo in new:
        best_offset, best_load = 0, None
        for offset in range(CYCLE_DAYS):
            trial = load[:]
            for slot in combo.slots(offset):
                trial[slot] += 1
            score = (max(trial), sum(x * x for x in trial))
            if best_load is None or score < best_load:
                best_offset, best_load = offset, score
        result[combo.key] = best_offset
        for slot in combo.slots(best_offset):
            load[slot] += 1
    return result


def plan_day(combos: list[Combo], offsets: dict[str, int], day: date) -> list[PageTask]:
    """Pages to fetch on ``day``; ``offsets`` must cover every combo."""
    slot = slot_for(day)
    tasks: list[PageTask] = []
    for combo in sorted(combos, key=lambda c: (c.category, c.area.code)):
        for index, page_slot in enumerate(combo.slots(offsets[combo.key])):
            if page_slot == slot:
                tasks.append(
                    PageTask(
                        category=combo.category,
                        area_code=combo.area.code,
                        area_name=combo.area.name,
                        slug=combo.area.slug or "",
                        page=index + 1,
                        pages=combo.pages,
                        expected_total=combo.area.count,
                    )
                )
    return tasks

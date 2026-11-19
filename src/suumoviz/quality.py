"""Quality gate for a day snapshot: bad parses must not reach the data branch."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from suumoviz.categories import PAGE_SIZE
from suumoviz.store import Row

TOTAL_TOLERANCE_ABS = 5  # header total vs. city-page count
TOTAL_TOLERANCE_REL = 0.05
ITEM_MISMATCH_SHARE = 0.05  # share of pages allowed to have an unexpected item count
MIN_SAMPLE = 20  # field-rate checks need at least this many listings in a category
PRICE_PARSE_RATE = 0.99
AREA_PARSE_RATE = 0.95
CONDOS = ("used_condo", "new_condo")
HOUSES = ("new_house", "used_house")


@dataclass
class Quality:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        return "ok" if self.ok else ";".join(self.problems[:10])


def _int(value: str) -> int | None:
    return int(value) if value not in ("", None) else None


def check_quality(pages: list[Row], listings: list[Row]) -> Quality:
    quality = Quality()
    ok_pages = [p for p in pages if p["status"] == "ok"]
    if not ok_pages:
        quality.problems.append("no_pages")
        return quality

    mismatched = 0
    for page in ok_pages:
        where = f"{page['category']}:{page['area_code']}:p{page['page']}"
        total, expected = _int(page["total"]), _int(page["expected_total"]) or 0
        if total is None:
            quality.problems.append(f"no_total:{where}")
            continue
        if abs(total - expected) > max(TOTAL_TOLERANCE_ABS, TOTAL_TOLERANCE_REL * expected):
            quality.problems.append(f"total_mismatch:{where}:{expected}->{total}")
        expected_items = min(PAGE_SIZE, max(0, total - (int(page["page"]) - 1) * PAGE_SIZE))
        if int(page["items"]) != expected_items:
            mismatched += 1
    if mismatched > max(1, int(ITEM_MISMATCH_SHARE * len(ok_pages))):
        quality.problems.append(f"item_count_mismatch:{mismatched}/{len(ok_pages)}")

    by_category: dict[str, list[Row]] = defaultdict(list)
    for row in listings:
        by_category[row["category"]].append(row)
    for category, rows in sorted(by_category.items()):
        if len(rows) < MIN_SAMPLE:
            continue
        if any(not r["price_raw"] for r in rows):
            quality.problems.append(f"missing_price_raw:{category}")
        if any(not r["address"] for r in rows):
            quality.problems.append(f"missing_address:{category}")
        priced = [r for r in rows if r["price_raw"] and "未定" not in r["price_raw"]]
        if priced and _rate(priced, "price_min") < PRICE_PARSE_RATE:
            quality.problems.append(f"price_parse_rate:{category}:{_rate(priced, 'price_min'):.3f}")
        area_field = "area_min" if category in CONDOS else "land_min"
        if _rate(rows, area_field) < AREA_PARSE_RATE:
            quality.problems.append(
                f"{area_field}_parse_rate:{category}:{_rate(rows, area_field):.3f}"
            )
    return quality


def _rate(rows: list[Row], key: str) -> float:
    return sum(1 for r in rows if r.get(key)) / len(rows)

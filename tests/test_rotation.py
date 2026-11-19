from collections import Counter
from datetime import date, timedelta

import pytest

from suumoviz.categories import CATEGORIES
from suumoviz.models import Area
from suumoviz.parse import parse_city_page
from suumoviz.rotation import (
    CYCLE_DAYS,
    EPOCH,
    Combo,
    assign_offsets,
    build_combos,
    daily_load,
    plan_day,
    slot_for,
)


@pytest.fixture
def combos(fixture_bytes) -> list[Combo]:
    areas = {
        key: parse_city_page(fixture_bytes(f"city_{key}.html"), category)
        for key, category in CATEGORIES.items()
    }
    return build_combos(areas)


def test_slot_for() -> None:
    assert slot_for(EPOCH) == 0
    assert slot_for(EPOCH + timedelta(days=7)) == 0
    assert slot_for(date(2026, 11, 7)) == 5
    assert slot_for(EPOCH - timedelta(days=1)) == 6


def test_combos_from_city_pages(combos: list[Combo]) -> None:
    assert len(combos) == 193
    assert sum(c.pages for c in combos) == 698
    assert all(c.area.count > 0 and c.area.slug for c in combos)


def test_balanced_daily_load(combos: list[Combo]) -> None:
    offsets = assign_offsets(combos, {})
    load = daily_load(combos, offsets)
    assert sum(load) == 698
    assert all(95 <= pages <= 105 for pages in load), load


def test_every_page_exactly_once_per_cycle(combos: list[Combo]) -> None:
    offsets = assign_offsets(combos, {})
    seen = Counter(
        (task.category, task.area_code, task.page)
        for day in range(CYCLE_DAYS)
        for task in plan_day(combos, offsets, EPOCH + timedelta(days=day))
    )
    expected = {(c.category, c.area.code, page) for c in combos for page in range(1, c.pages + 1)}
    assert set(seen) == expected
    assert set(seen.values()) == {1}


def test_new_condo_pages_share_one_day(combos: list[Combo]) -> None:
    offsets = assign_offsets(combos, {})
    chuo = next(c for c in combos if c.category == "new_condo" and c.area.code == "13102")
    assert chuo.pages == 2
    assert len(set(chuo.slots(offsets[chuo.key]))) == 1


def test_address_sorted_pages_spread_across_days(combos: list[Combo]) -> None:
    offsets = assign_offsets(combos, {})
    setagaya = next(c for c in combos if c.category == "used_condo" and c.area.code == "13112")
    per_day = Counter(setagaya.slots(offsets[setagaya.key]))
    assert setagaya.pages == 23
    assert sorted(per_day.values()) == [3, 3, 3, 3, 3, 4, 4]


def test_existing_offsets_are_kept_and_new_combo_goes_to_lightest_slot(
    combos: list[Combo],
) -> None:
    offsets = assign_offsets(combos, {})
    load = daily_load(combos, offsets)
    newcomer = Combo("used_house", Area("13999", "テスト村", 50, "sc_test"))
    updated = assign_offsets([*combos, newcomer], offsets)
    assert {k: updated[k] for k in offsets} == offsets
    assert updated[newcomer.key] == load.index(min(load))


def test_tasks_carry_urls_and_expected_totals(combos: list[Combo]) -> None:
    offsets = assign_offsets(combos, {})
    tasks = plan_day(combos, offsets, date(2026, 11, 7))
    assert 95 <= len(tasks) <= 105
    task = tasks[0]
    assert task.url == CATEGORIES[task.category].list_url(task.slug, task.page)
    assert task.expected_total > 0


def test_zero_count_and_unlinked_areas_are_skipped() -> None:
    areas = {
        "used_condo": [
            Area("13101", "千代田区", 0, "sc_chiyoda"),
            Area("13102", "中央区", 10, None),
            Area("13103", "港区", 250, "sc_minato"),
        ]
    }
    combos = build_combos(areas)
    assert [c.key for c in combos] == ["used_condo:13103"]
    assert combos[0].pages == 3

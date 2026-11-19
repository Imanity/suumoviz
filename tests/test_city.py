import pytest

from suumoviz.categories import CATEGORIES
from suumoviz.parse import parse_city_page

# Observed on 2026-11-07 (see tests/fixtures/README.md)
EXPECTED = {
    "used_condo": ("city_used_condo.html", 49, 36_894),
    "new_condo": ("city_new_condo.html", 43, 880),
    "new_house": ("city_new_house.html", 50, 12_023),
    "used_house": ("city_used_house.html", 51, 8_518),
}


@pytest.mark.parametrize("category", list(EXPECTED))
def test_city_page_counts_and_slugs(category: str, fixture_bytes) -> None:
    filename, municipalities, total = EXPECTED[category]
    areas = parse_city_page(fixture_bytes(filename), CATEGORIES[category])

    with_listings = [area for area in areas if area.count > 0]
    assert len(with_listings) == municipalities
    assert sum(area.count for area in areas) == total
    assert len({area.code for area in areas}) == len(areas)
    assert all(area.code.startswith("13") and len(area.code) == 5 for area in areas)
    # every municipality that has listings must be crawlable
    assert all(area.slug and area.slug.startswith("sc_") for area in with_listings)


def test_city_page_known_entries(fixture_bytes) -> None:
    areas = {
        a.code: a
        for a in parse_city_page(fixture_bytes("city_used_condo.html"), CATEGORIES["used_condo"])
    }
    assert areas["13112"].name == "世田谷区"
    assert areas["13112"].count == 2207
    assert areas["13112"].slug == "sc_setagaya"
    assert areas["13103"].slug == "sc_minato"
    assert areas["13103"].count == 3510
    # municipalities without listings are still reported, with count 0
    assert areas["13421"].name == "小笠原村"
    assert areas["13421"].count == 0


def test_city_page_new_condo_slugs_from_labels(fixture_bytes) -> None:
    areas = {
        a.code: a
        for a in parse_city_page(fixture_bytes("city_new_condo.html"), CATEGORIES["new_condo"])
    }
    assert areas["13102"].name == "中央区"
    assert areas["13102"].count == 166
    assert areas["13102"].slug == "sc_chuo"

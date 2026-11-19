from suumoviz.categories import CATEGORIES
from suumoviz.parse import parse_list_page


def parse(fixture_bytes, filename: str, category: str):
    return parse_list_page(fixture_bytes(filename), CATEGORIES[category])


def test_used_condo_first_page(fixture_bytes) -> None:
    page = parse(fixture_bytes, "list_used_condo_setagaya_p1.html", "used_condo")
    assert page.total == 2211
    assert page.errors == ()
    assert [x.listing_id for x in page.listings] == [
        "22106672",
        "21982617",
        "20733378",
        "21870922",
        "21895565",
    ]
    first = page.listings[0]
    assert first.category == "used_condo"
    assert first.name == "グランデュオ三宿"
    assert (first.price_min, first.price_max) == (42_800_000, 42_800_000)
    assert first.price_raw == "4280万円"
    assert first.address == "東京都世田谷区三宿1-1-4"
    assert (first.line, first.station, first.walk_min) == ("東急田園都市線", "三軒茶屋", 8)
    assert (first.area_min, first.area_max) == (25.11, 25.11)
    assert first.layout == "1K"
    assert first.balcony == 3.93
    assert first.built_ym == "2012-01"
    assert first.labels == ("新着",)
    assert first.land_min is None and first.delivery_raw is None
    assert first.path == "/ms/chuko/tokyo/sc_setagaya/nc_22106672/"  # query string dropped

    no_balcony = page.listings[3]
    assert no_balcony.balcony is None  # shown as "-"

    oku = page.listings[4]
    assert oku.price_min == 114_800_000
    assert oku.labels == ("価格更新",)


def test_used_condo_last_page_is_partial(fixture_bytes) -> None:
    page = parse(fixture_bytes, "list_used_condo_setagaya_p23.html", "used_condo")
    assert page.total == 2211
    assert len(page.listings) == 11  # 2,211 = 22 full pages + 11
    assert len({x.listing_id for x in page.listings}) == 11
    assert all(x.price_min and x.area_min and x.address for x in page.listings)


def test_new_condo_cassettes(fixture_bytes) -> None:
    page = parse(fixture_bytes, "list_new_condo_chuo_p1.html", "new_condo")
    assert page.total == 169
    assert [x.listing_id for x in page.listings] == ["67737844", "67727473", "67728904"]

    undecided = page.listings[0]
    assert undecided.name == "SYFORME 京橋(シーフォルム京橋)"
    assert undecided.price_raw == "価格未定"
    assert (undecided.price_min, undecided.price_max) == (None, None)
    assert undecided.address == "中央区八丁堀3"
    assert undecided.path == "/ms/shinchiku/tokyo/sc_chuo/nc_67737844/"
    assert (undecided.line, undecided.station, undecided.walk_min) == ("都営浅草線", "宝町", 4)
    assert (undecided.area_min, undecided.area_max) == (35.24, 56.03)
    assert undecided.layout == "1LDK"
    assert undecided.delivery_raw == "2027年3月下旬予定"

    ranged = page.listings[1]
    assert (ranged.price_min, ranged.price_max) == (99_000_000, 260_000_000)
    assert (ranged.area_min, ranged.area_max) == (38.08, 80.63)
    assert ranged.layout == "1LDK~3LDK"


def test_new_house_ranges_land_and_undecided(fixture_bytes) -> None:
    page = parse(fixture_bytes, "list_new_house_setagaya_p1.html", "new_house")
    assert page.total == 670
    by_id = {x.listing_id: x for x in page.listings}
    assert len(by_id) == 5

    ranged = by_id["21992387"]
    assert (ranged.price_min, ranged.price_max) == (159_800_000, 162_800_000)
    assert (ranged.area_min, ranged.area_max) == (112.39, 114.27)
    assert (ranged.land_min, ranged.land_max) == (64.87, 64.88)
    assert ranged.layout == "2LDK+2S(納戸)"

    unnamed = by_id["21597652"]
    assert unnamed.name is None

    land_only = by_id["21916513"]  # land plot listed under new houses: building area "-"
    assert land_only.path == "/tochi/tokyo/sc_setagaya/nc_21916513/"
    assert ranged.path == "/ikkodate/tokyo/sc_setagaya/nc_21992387/"
    assert land_only.area_min is None
    assert land_only.layout is None
    assert land_only.land_min == 190.9

    undecided = by_id["22106824"]
    assert undecided.price_raw == "未定"
    assert undecided.price_min is None
    assert undecided.labels == ("新着",)


def test_used_house_built_and_bus_access(fixture_bytes) -> None:
    page = parse(fixture_bytes, "list_used_house_setagaya_p1.html", "used_house")
    assert page.total == 759
    by_id = {x.listing_id: x for x in page.listings}

    first = by_id["21601967"]
    assert first.path == "/chukoikkodate/tokyo/sc_setagaya/nc_21601967/"
    assert first.price_min == 139_800_000
    assert (first.area_min, first.land_min) == (105.54, 73.74)
    assert first.built_ym == "2009-10"

    bus = by_id["21675148"]
    assert (bus.line, bus.station, bus.walk_min) == ("東急田園都市線", "用賀", None)
    # "84.89m2(25.67坪)(登記)、うち地下室27.27m2": the basement note is not a range
    assert (bus.area_min, bus.area_max) == (84.89, 84.89)


def test_page_without_listings(fixture_bytes) -> None:
    page = parse_list_page(b"<html><body><p>no results</p></body></html>", CATEGORIES["used_condo"])
    assert page.total is None
    assert page.listings == ()

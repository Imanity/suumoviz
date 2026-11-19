import pytest

from suumoviz.geocode import Geocoder, kanji_number, split_chome


def town(
    code: str, city: str, city_name: str, name: str, lat: float, lng: float, estat: str = ""
) -> dict:
    return {
        "town_code": code,
        "city_code": city,
        "city_name": city_name,
        "town_name": name,
        "lat": str(lat),
        "lng": str(lng),
        "estat_code": estat,
    }


ROWS = [
    town("131010002001", "13101", "千代田区", "霞が関一丁目", 35.670, 139.750, "13101023001"),
    town("131010002003", "13101", "千代田区", "霞が関三丁目", 35.674, 139.746, "13101023003"),
    town("131010001001", "13101", "千代田区", "内幸町一丁目", 35.671, 139.758),
    town("132090001000", "13209", "町田市", "本町田", 35.570, 139.440),
    town("132090002001", "13209", "町田市", "本町一丁目", 35.540, 139.450, "13209010001"),
    town("132090002002", "13209", "町田市", "本町二丁目", 35.541, 139.451, "13209011002"),
    town("133030001000", "13303", "西多摩郡瑞穂町", "大字箱根ケ崎", 35.770, 139.350),
    town("133030002002", "13303", "西多摩郡瑞穂町", "南平二丁目", 35.760, 139.340),
    town("133050001000", "13305", "西多摩郡日の出町", "大字平井", 35.740, 139.260),
    town("133810001000", "13381", "三宅村", "坪田", 34.060, 139.550),
]


@pytest.fixture(scope="module")
def geo() -> Geocoder:
    return Geocoder(ROWS)


@pytest.mark.parametrize(
    ("text", "value"),
    [("一", 1), ("九", 9), ("十", 10), ("十二", 12), ("二十", 20), ("二十一", 21)],
)
def test_kanji_number(text: str, value: int) -> None:
    assert kanji_number(text) == value


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("霞が関一丁目", ("霞が関", 1)),
        ("麻布十番一丁目", ("麻布十番", 1)),
        ("西新宿十二丁目", ("西新宿", 12)),
        ("大楽寺町", ("大楽寺町", None)),
        ("青海二丁目地先", ("青海二丁目地先", None)),
    ],
)
def test_split_chome(name: str, expected: tuple[str, int | None]) -> None:
    assert split_chome(name) == expected


@pytest.mark.parametrize(
    "address",
    [
        "東京都千代田区霞が関3",
        "東京都千代田区霞が関3-1-1",
        "東京都千代田区霞が関３",  # full-width digit
        "千代田区霞が関三丁目",  # new condo pages omit 東京都
        "東京都千代田区霞が関3-805番14他(地番)",
    ],
)
def test_chome_match(geo: Geocoder, address: str) -> None:
    place = geo.locate(address, "13101")
    assert place is not None
    assert (place.id, place.name, place.precision) == ("131010002003", "霞が関三丁目", "chome")


def test_missing_chome_falls_back_to_town_centroid(geo: Geocoder) -> None:
    place = geo.locate("東京都千代田区霞が関2", "13101")
    assert place is not None
    assert (place.id, place.name, place.precision) == ("13101:霞が関", "霞が関", "town")
    assert (place.lat, place.lng) == (35.672, 139.748)


def test_unknown_town_falls_back_to_city(geo: Geocoder) -> None:
    place = geo.locate("東京都千代田区永田町1", "13101")
    assert place is not None
    assert (place.id, place.precision) == ("13101", "city")
    assert place.lat == pytest.approx((35.670 + 35.674 + 35.671) / 3, abs=1e-6)


def test_longest_town_name_wins(geo: Geocoder) -> None:
    assert geo.locate("東京都町田市本町田123", "13209").id == "132090001000"
    assert geo.locate("東京都町田市本町1-2", "13209").id == "132090002001"


def test_oaza_gun_and_small_ke(geo: Geocoder) -> None:
    hakone = geo.locate("東京都西多摩郡瑞穂町大字箱根ヶ崎715番9", "13300")
    assert (hakone.id, hakone.precision) == ("133030001000", "chome")
    assert geo.locate("東京都瑞穂町南平2-38", "13300").id == "133030002002"  # 郡 omitted
    assert geo.locate("東京都西多摩郡日の出町大字平井2290-6番", "13300").id == "133050001000"
    assert geo.locate("東京都三宅島三宅村坪田", "13381").id == "133810001000"  # SUUMO spelling


def test_address_city_wins_over_area_code(geo: Geocoder) -> None:
    assert geo.locate("東京都町田市本町田1", "13101").city_code == "13209"


def test_area_code_fallback_and_groups(geo: Geocoder) -> None:
    assert geo.locate(None, "13101").id == "13101"
    assert geo.locate("住所非公開", "13209").id == "13209"
    group = geo.area_point("13300", "西多摩郡")
    assert (group.id, group.name, group.precision) == ("13300", "西多摩郡", "city")
    assert group.lat == pytest.approx((35.765 + 35.740) / 2, abs=1e-6)
    assert geo.locate(None, "13300").id == "13300"
    assert geo.locate(None, "99999") is None
    assert geo.area_point("13420") is None  # no member municipality in this small table


def test_area_codes(geo: Geocoder) -> None:
    chome = geo.locate("東京都千代田区霞が関3-2-1", "13101")
    assert geo.area_codes(chome) == ("13101", "131010230", "13101023003")
    town = geo.locate("東京都千代田区霞が関", "13101")  # town centroid: chome unknown
    assert geo.area_codes(town) == ("13101", "131010230", None)
    split = geo.locate("東京都町田市本町", "13209")  # its chome lie in two e-Stat towns
    assert geo.area_codes(split) == ("13209", None, None)
    unmapped = geo.locate("東京都千代田区内幸町1", "13101")  # no estat_code
    assert geo.area_codes(unmapped) == ("13101", None, None)
    assert geo.area_codes(geo.locate(None, "13209")) == ("13209", None, None)
    assert geo.area_codes(geo.locate(None, "13300")) == (None, None, None)  # SUUMO group


def test_shipped_reference_data() -> None:
    geo = Geocoder.load()
    assert len(geo.cities) == 62
    kasumi = geo.locate("東京都千代田区霞が関3", "13101")
    assert (kasumi.id, kasumi.name, kasumi.precision) == ("131010002003", "霞が関三丁目", "chome")
    assert geo.locate("中央区八丁堀3", "13102").name == "八丁堀三丁目"
    assert geo.locate("東京都西多摩郡瑞穂町大字箱根ケ崎", "13300").precision == "chome"
    for group in ("13300", "13360", "13380", "13400", "13420"):
        assert geo.area_point(group) is not None
    assert geo.area_codes(kasumi) == ("13101", "131010050", "13101005003")

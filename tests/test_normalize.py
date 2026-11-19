import pytest

from suumoviz.parse.normalize import (
    clean,
    parse_access,
    parse_area_range,
    parse_int,
    parse_price_range,
    parse_year_month,
)


def test_clean_nfkc_and_whitespace() -> None:
    assert clean("　東京都世田谷区三宿１-1-4\n ") == "東京都世田谷区三宿1-1-4"
    assert clean("25.11㎡（7.59坪）") == "25.11m2(7.59坪)"
    assert clean("  ") is None
    assert clean(None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4280万円", (42_800_000, 42_800_000)),
        ("１億３９８０万円", (139_800_000, 139_800_000)),
        ("1億円", (100_000_000, 100_000_000)),
        ("1億5980万円～1億6280万円", (159_800_000, 162_800_000)),
        ("9900万円~2億6000万円 (先着順受付)", (99_000_000, 260_000_000)),
        ("6300万円台～3億3700万円台/予定", (63_000_000, 337_000_000)),
        ("3,980万円", (39_800_000, 39_800_000)),
        ("5,000円", (5_000, 5_000)),
        ("4,980.5万円", (49_805_000, 49_805_000)),
        ("価格未定", (None, None)),
        ("未定", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_price_range(text: str | None, expected: tuple[int | None, int | None]) -> None:
    assert parse_price_range(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("25.11m2（7.59坪）（壁芯）", (25.11, 25.11)),
        ("64.87m2～64.88m2（19.62坪～19.62坪）（登記）", (64.87, 64.88)),
        ("35.24m2・56.03m2", (35.24, 56.03)),
        ("100.4m2(実測)、うち1階車庫12.11m2", (100.4, 100.4)),
        ("84.89m2(25.67坪)(登記)、うち地下室27.27m2", (84.89, 84.89)),
        ("93.1m2(28.16坪)、路地状部分:20.75m2含", (93.1, 93.1)),
        ("82m2~84m2", (82.0, 84.0)),
        ("12.5㎡", (12.5, 12.5)),
        ("-", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_area_range(text: str | None, expected: tuple[float | None, float | None]) -> None:
    assert parse_area_range(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("東急田園都市線「三軒茶屋」徒歩8分", ("東急田園都市線", "三軒茶屋", 8)),
        ("東急田園都市線「用賀」バス5分停歩3分", ("東急田園都市線", "用賀", None)),
        ("都営浅草線/宝町 徒歩4分", ("都営浅草線", "宝町", 4)),
        ("ＪＲ山手線「新宿」徒歩１０分", ("JR山手線", "新宿", 10)),
        ("徒歩5分", (None, None, 5)),
        (None, (None, None, None)),
    ],
)
def test_parse_access(
    text: str | None, expected: tuple[str | None, str | None, int | None]
) -> None:
    assert parse_access(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2012年1月", "2012-01"),
        ("１９７５年１２月", "1975-12"),
        ("2027年3月下旬予定", "2027-03"),
        ("2012年13月", None),
        ("即入居可", None),
        (None, None),
    ],
)
def test_parse_year_month(text: str | None, expected: str | None) -> None:
    assert parse_year_month(text) == expected


def test_parse_int() -> None:
    assert parse_int(" 2,211件 ") == 2211
    assert parse_int("件") is None

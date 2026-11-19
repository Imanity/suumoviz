import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from suumoviz import build, codec
from suumoviz.build import BuildError, build_site, timeline
from suumoviz.cli import main
from suumoviz.geocode import Geocoder
from suumoviz.state import JST
from suumoviz.store import (
    ARCHIVE_FIELDS,
    COUNT_FIELDS,
    EVENT_FIELDS,
    LISTING_FIELDS,
    RUN_FIELDS,
    write_rows,
)

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=JST)
D0 = date(2026, 11, 1)  # first of 12 completed runs: the timeline is 11-09 … 11-12


def day(offset: int) -> str:
    return (D0 + timedelta(days=offset)).isoformat()


TIMELINE = [day(8), day(9), day(10), day(11)]

GEO_ROWS = [
    {
        "town_code": code,
        "city_code": code[:5],
        "city_name": city,
        "town_name": name,
        "lat": "35.6",
        "lng": "139.7",
        "estat_code": estat,
    }
    for code, city, name, estat in [
        ("131010002001", "千代田区", "霞が関一丁目", "13101005001"),
        ("131010002002", "千代田区", "霞が関二丁目", "13101005002"),
        ("131130001001", "渋谷区", "神南一丁目", "13113001001"),
    ]
]
KASUMI1, KASUMI2 = "東京都千代田区霞が関1", "東京都千代田区霞が関2"


def listing(listing_id: str, price: str, **values: str) -> dict[str, str]:
    row = dict.fromkeys(LISTING_FIELDS, "")
    row.update(
        listing_id=listing_id,
        category="used_condo",
        area_code="13101",
        address=KASUMI1,
        price_min=price,
        area_min="50",
        first_seen=day(0),
        last_seen=day(7),
        status="active",
    )
    row.update(values)
    return row


def event(when: str, listing_id: str, kind: str, price: str, category: str = "used_condo") -> dict:
    return {
        "date": when,
        "category": category,
        "area_code": "13101",
        "listing_id": listing_id,
        "type": kind,
        "price_min": price,
    }


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    write_rows(
        data / "listings" / "used_condo.csv",
        LISTING_FIELDS,
        [
            # 60M until day 10, then 50M (events); on sale through day 11 (last seen day 7)
            listing("100", "50000000"),
            listing("101", "70000000"),
            listing("102", "140000000", area_min="70"),
            # last seen day 0: on sale until day 8 (grace 9 days), gone from day 9
            listing("103", "10000000", last_seen=day(0)),
            # first seen day 10
            listing("104", "90000000", first_seen=day(10), last_seen=day(10)),
            listing("105", "", address=KASUMI2),  # 価格未定: counted, no price
            listing("106", "30000000", area_code="13113", address="東京都渋谷区神南1"),
            listing("107", "40000000", address="住所非公開"),  # municipality only
            listing("108", "60000000", area_code="13300", address=""),  # SUUMO group: Tokyo
        ],
    )
    write_rows(
        data / "archive" / "2026.csv",
        ARCHIVE_FIELDS,
        [  # pruned from listings/; last seen day 2, so on sale until day 10
            {
                "listing_id": "109",
                "category": "used_condo",
                "area_code": "13101",
                "address": KASUMI1,
                "price_min": "80000000",
                "area_min": "40",
                "first_seen": day(0),
                "last_seen": day(2),
                "delisted_on": day(17),
            }
        ],
    )
    write_rows(
        data / "listings" / "new_condo.csv",
        LISTING_FIELDS,
        [  # unit price only from a single price and a single floor area
            listing(str(200 + i), str(price), category="new_condo", **extra)
            for i, (price, extra) in enumerate(
                [
                    (60_000_000, {}),
                    (70_000_000, {}),
                    (80_000_000, {}),
                    (50_000_000, {"price_max": "90000000", "area_max": "80"}),
                ]
            )
        ],
    )
    write_rows(
        data / "events" / "2026-11.csv",
        EVENT_FIELDS,
        [
            event(day(0), "100", "new", "60000000"),
            event(day(10), "100", "price_change", "50000000"),
            event(day(0), "101", "new", "70000000"),
        ],
    )
    write_rows(
        data / "counts" / "2026.csv",
        COUNT_FIELDS,
        [
            dict(zip(COUNT_FIELDS, [day(11), "used_condo", code, name, n], strict=True))
            for code, name, n in [("13101", "千代田区", "690"), ("13113", "渋谷区", "400")]
        ],
    )
    runs = [{"date": day(i), "status": "completed", "merged": "true"} for i in range(12)] + [
        {"date": day(12), "status": "failed", "merged": "false"}
    ]
    write_rows(data / "runs.csv", RUN_FIELDS, runs)
    return data


@pytest.fixture
def geo() -> Geocoder:
    return Geocoder(GEO_ROWS)


def load(path: Path) -> dict:
    assert codec.is_encoded(path.read_bytes())
    return json.loads(codec.read_text(path))


def table(out: Path, when: str, category: str = "used_condo") -> dict[str, dict]:
    doc = load(out / "day" / when / f"{category}.dat")
    return {r[0]: dict(zip(doc["fields"], r, strict=True)) for r in doc["rows"]}


def tokyo(index: dict, category: str = "used_condo") -> list[dict | None]:
    entry = next(c for c in index["categories"] if c["key"] == category)
    return [dict(zip(index["fields"], v, strict=True)) if v else None for v in entry["tokyo"]]


def test_index(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    result = build_site(data_dir, out, geocoder=geo, now=NOW)
    assert sorted(p.name for p in out.iterdir()) == ["day", "history", "index.dat"]
    index = load(out / "index.dat")
    assert index["version"] == 3
    assert index["generated_at"] == "2026-11-12T08:00:00+09:00"
    assert (index["first_date"], index["latest_date"]) == (day(0), day(11))  # day 12 not merged
    assert index["complete"] is True
    assert index["dates"] == TIMELINE
    assert (index["grace_days"], index["min_sample"]) == (9, 3)
    assert "e-Stat" in index["sources"]["boundaries"]
    assert [c["key"] for c in index["categories"]] == [
        "used_condo", "new_condo", "new_house", "used_house",
    ]  # fmt: skip
    used = next(c for c in index["categories"] if c["key"] == "used_condo")
    assert used["official"] == [None, None, None, 1090]
    assert [v["count"] if v else None for v in tokyo(index)] == [9, 8, 9, 8]
    assert tokyo(index, "new_house") == [None] * 4
    assert result.dates == TIMELINE
    assert result.listings["used_condo"] == 8
    assert result.areas["used_condo"] == {"city": 2, "town": 2, "chome": 3}


def test_on_sale_window_and_prices(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    first, second, third = (table(out, d)["13101005001"] for d in TIMELINE[:3])
    # day 8: 100 (60M), 101, 102, 103 (last seen day 0), 109 (archived)
    assert (first["count"], first["n"], first["mean"]) == (5, 5, 7200)
    # day 9: 103 is gone
    assert (second["count"], second["mean"], second["median"]) == (4, 8750, 7500)
    # day 10: 100 dropped to 50M, 104 appeared
    assert (third["count"], third["mean"], third["median"]) == (5, 8600, 8000)
    assert third["unit_n"] == 5
    assert third["unit_mean"] == round((100 + 140 + 200 + 200 + 180) / 5, 1)


def test_levels(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    values = table(out, day(11))
    assert sorted(values) == [
        "13101", "131010050", "13101005001", "13101005002", "13113", "131130010", "13113001001",
    ]  # fmt: skip
    assert values["13101"]["count"] == 6  # 100-102, 104, 105, 107 (109 gone since day 11)
    assert values["131010050"]["count"] == 5  # without 107 (address unknown)
    assert values["13101005002"] == {
        "code": "13101005002", "count": 1, "n": 0, "mean": None, "median": None,
        "unit_n": 0, "unit_mean": None, "unit_median": None,
    }  # fmt: skip


def test_small_samples_hide_prices(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    shibuya = table(out, day(11))["13113"]
    assert (shibuya["count"], shibuya["n"], shibuya["mean"], shibuya["unit_mean"]) == (
        1, 1, None, None,
    )  # fmt: skip


def test_unit_price_needs_single_price_and_area(
    data_dir: Path, geo: Geocoder, tmp_path: Path
) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    condo = table(out, day(11), "new_condo")["13101"]
    assert (condo["n"], condo["mean"]) == (4, 6500)
    assert (condo["unit_n"], condo["unit_mean"], condo["unit_median"]) == (3, 140.0, 140.0)


def test_history_files(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    names = sorted(p.relative_to(out / "history").as_posix() for p in (out / "history").rglob("*"))
    assert "used_condo/13000.dat" in names  # municipalities
    assert "used_condo/13101.dat" in names  # its towns
    assert "used_condo/131010050.dat" in names  # that town's chome
    towns = load(out / "history" / "used_condo" / "13101.dat")
    assert (towns["parent"], towns["dates"]) == ("13101", TIMELINE)
    assert list(towns["series"]) == ["131010050"]
    counts = [v[0] if v else None for v in towns["series"]["131010050"]]
    assert counts == [6, 5, 6, 5]
    chome = load(out / "history" / "used_condo" / "131010050.dat")["series"]
    assert chome["13101005002"][0] == [1, 0, None, None, 0, None, None]


def test_no_single_listing_is_published(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, geocoder=geo, now=NOW)
    text = "".join(codec.read_text(p) for p in out.rglob("*.dat"))
    for listing_id in ("100", "101", "102", "104", "106", "109", "200"):
        assert f'"{listing_id}"' not in text
    assert "霞が関" not in text


def test_timeline_before_a_full_rotation() -> None:
    runs = [{"date": day(i), "status": "completed", "merged": "true"} for i in range(8)]
    assert timeline(runs) == ([day(7)], False)  # needs day 0 + 8
    assert timeline([]) == ([], False)


def test_timeline_keeps_old_days_weekly() -> None:
    runs = [{"date": day(i), "status": "completed", "merged": "true"} for i in range(130)]
    days, complete = timeline(runs)
    assert complete
    start, latest = D0 + timedelta(days=8), D0 + timedelta(days=129)
    daily_from = latest - timedelta(days=89)
    for d in days:
        value = date.fromisoformat(d)
        assert value >= start
        assert value >= daily_from or (value - start).days % 7 == 0
    assert days[0] == start.isoformat() and days[-1] == latest.isoformat()
    assert len([d for d in days if date.fromisoformat(d) >= daily_from]) == 90


def test_rebuild_replaces_old_output(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    out = tmp_path / "site"
    (out / "day" / "2020-01-01").mkdir(parents=True)
    (out / "summary.dat").write_text("old")
    (out / "keep.txt").write_text("not ours")
    build_site(data_dir, out, geocoder=geo, now=NOW)
    assert sorted(p.name for p in (out / "day").iterdir()) == TIMELINE
    assert not (out / "summary.dat").exists()
    assert (out / "keep.txt").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".site-")]  # no staging left


def test_build_is_deterministic(data_dir: Path, geo: Geocoder, tmp_path: Path) -> None:
    build_site(data_dir, tmp_path / "a", geocoder=geo, now=NOW)
    build_site(data_dir, tmp_path / "b", geocoder=geo, now=NOW)
    for path in (tmp_path / "a").rglob("*.dat"):
        assert path.read_bytes() == (tmp_path / "b" / path.relative_to(tmp_path / "a")).read_bytes()


def test_oversized_output_writes_nothing(
    data_dir: Path, geo: Geocoder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "MAX_FILE_BYTES", 200)
    out = tmp_path / "site"
    with pytest.raises(BuildError, match="over 200"):
        build_site(data_dir, out, geocoder=geo, now=NOW)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == [data_dir]


def test_build_needs_a_merged_run(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="no merged run"):
        build_site(tmp_path / "data", tmp_path / "site")


def test_cli_build(data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "site"
    assert main(["build", "--data-dir", str(data_dir), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("build: ") and '"dates": ["2026-11-09", "2026-11-12", 4]' in printed
    assert (out / "index.dat").exists()
    assert main(["build", "--data-dir", str(tmp_path / "empty"), "--out", str(out)]) == 1

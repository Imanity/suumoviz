import json
from datetime import datetime
from pathlib import Path

import pytest

from suumoviz import build, codec
from suumoviz.build import BuildError, build_site
from suumoviz.cli import main
from suumoviz.state import JST
from suumoviz.store import COUNT_FIELDS, LISTING_FIELDS, RUN_FIELDS, write_rows

D1, D2, D3 = "2026-11-07", "2026-11-08", "2026-11-09"
NOW = datetime(2026, 11, 9, 8, 0, tzinfo=JST)


def listing(listing_id: str, price: str, **values: str) -> dict[str, str]:
    row = dict.fromkeys(LISTING_FIELDS, "")
    row.update(
        listing_id=listing_id,
        category="used_condo",
        area_code="13101",
        price_min=price,
        price_max=price,
        area_min="50",
        area_max="50",
        first_seen=D1,
        last_seen=D2,
        status="active",
    )
    row.update(values)
    return row


def count(day: str, category: str, code: str, name: str, n: int) -> dict[str, str]:
    return dict(zip(COUNT_FIELDS, [day, category, code, name, str(n)], strict=True))


def run(day: str, merged: bool) -> dict[str, str]:
    return {"date": day, "status": "completed", "merged": "true" if merged else "false"}


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    write_rows(
        data / "listings" / "used_condo.csv",
        LISTING_FIELDS,
        [
            listing("100", "60000000"),
            listing("101", "70000000"),
            listing("102", "140000000"),
            listing("103", "999000000", status="inactive", delisted_on=D2),  # left out
            listing("104", ""),  # 価格未定: no price, not counted
            listing("105", "30000000", area_code="13113", area_min="25", area_max="25"),
        ],
    )
    write_rows(
        data / "listings" / "new_house.csv",
        LISTING_FIELDS,
        [  # land-only listing: has a price but no building area → no unit price
            listing("200", "39800000", category="new_house", area_code="13300", area_min=""),
        ],
    )
    write_rows(
        data / "counts" / "2026.csv",
        COUNT_FIELDS,
        [
            count(D1, "used_condo", "13101", "千代田区", 687),
            count(D1, "new_house", "13300", "西多摩郡", 85),
            count(D2, "used_condo", "13101", "千代田区", 690),
            count(D2, "used_condo", "13113", "渋谷区", 400),
            count(D2, "used_condo", "13360", "大島支庁", 0),  # no listings anywhere: no row
            count(D2, "new_house", "13300", "西多摩郡", 86),
            count(D3, "used_condo", "13101", "千代田区", 691),  # latest day of used_condo
            count(D3, "used_condo", "13113", "渋谷区", 401),
        ],
    )
    write_rows(data / "runs.csv", RUN_FIELDS, [run(D1, True), run(D2, True), run(D3, False)])
    return data


def load(out: Path) -> dict:
    path = out / "summary.dat"
    assert codec.is_encoded(path.read_bytes())
    return json.loads(codec.read_text(path))


def values(summary: dict, category: str) -> dict[str, dict]:
    entry = next(c for c in summary["categories"] if c["key"] == category)
    return {r[0]: dict(zip(entry["fields"], r, strict=True)) for r in entry["rows"]}


def test_summary_has_area_averages(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    result = build_site(data_dir, out, now=NOW)
    assert [p.name for p in out.iterdir()] == ["summary.dat"]
    summary = load(out)
    assert summary["version"] == 2
    assert summary["generated_at"] == "2026-11-09T08:00:00+09:00"
    assert (summary["first_date"], summary["latest_date"]) == (D1, D2)  # D3 was not merged
    assert [c["key"] for c in summary["categories"]] == [
        "used_condo", "new_condo", "new_house", "used_house",
    ]  # fmt: skip

    condos = values(summary, "used_condo")
    assert list(condos) == ["13000", "13101", "13113"]
    assert condos["13101"] == {
        "area": "13101", "count": 691, "n": 3, "mean": 9000, "median": 7000, "unit_mean": 180.0,
    }  # fmt: skip
    assert condos["13113"] == {
        "area": "13113", "count": 401, "n": 1, "mean": 3000, "median": 3000, "unit_mean": 120.0,
    }  # fmt: skip
    tokyo = condos["13000"]
    assert (tokyo["count"], tokyo["n"], tokyo["mean"], tokyo["median"]) == (1092, 4, 7500, 6500)
    assert tokyo["unit_mean"] == 165.0  # (120 + 140 + 280 + 120) / 4

    houses = values(summary, "new_house")
    assert houses["13300"]["count"] == 86 and houses["13300"]["mean"] == 3980
    assert houses["13300"]["unit_mean"] is None  # land only
    assert values(summary, "new_condo") == {}

    assert result.areas == {"used_condo": 2, "new_condo": 0, "new_house": 1, "used_house": 0}
    assert result.listings == {"used_condo": 4, "new_condo": 0, "new_house": 1, "used_house": 0}


def test_summary_areas_have_points(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, now=NOW)
    summary = load(out)
    fields = summary["areas"]["fields"]
    areas = {r[0]: dict(zip(fields, r, strict=True)) for r in summary["areas"]["rows"]}
    assert list(areas) == ["13000", "13101", "13113", "13300", "13360"]
    assert areas["13000"]["name"] == "東京都"
    assert 35.6 < areas["13000"]["lat"] < 35.8  # mainland centre, not pulled south by islands
    assert areas["13101"]["name"] == "千代田区"
    assert areas["13300"]["lat"] is not None  # 西多摩郡 group point
    assert "国土交通省" in summary["sources"]["geo"]


def test_no_single_listing_is_published(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(data_dir, out, now=NOW)
    text = codec.read_text(out / "summary.dat")
    for listing_id in ("100", "101", "102", "105", "200"):
        assert f'"{listing_id}"' not in text


def test_build_is_deterministic(data_dir: Path, tmp_path: Path) -> None:
    build_site(data_dir, tmp_path / "a", now=NOW)
    build_site(data_dir, tmp_path / "b", now=NOW)
    assert (tmp_path / "a" / "summary.dat").read_bytes() == (
        tmp_path / "b" / "summary.dat"
    ).read_bytes()


def test_oversized_output_writes_nothing(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "MAX_FILE_BYTES", 200)
    out = tmp_path / "site"
    with pytest.raises(BuildError, match="over 200"):
        build_site(data_dir, out, now=NOW)
    assert not out.exists()


def test_build_needs_a_merged_run(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="no merged run"):
        build_site(tmp_path / "data", tmp_path / "site")


def test_cli_build(data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "site"
    assert main(["build", "--data-dir", str(data_dir), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("build: ") and '"used_condo": 4' in printed
    assert (out / "summary.dat").exists()
    assert main(["build", "--data-dir", str(tmp_path / "empty"), "--out", str(out)]) == 1

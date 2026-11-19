"""Convert MLIT 大字・町丁目レベル位置参照情報 (one prefecture zip) into the compact
UTF-8 CSV that ships with the geocoder.

    python tools/make_chome.py 13000-19.0b.zip src/suumoviz/geodata/tokyo_chome.csv

Download: https://nlftp.mlit.go.jp/isj/ → 大字・町丁目レベル → 東京都 (latest year).
After regenerating, update GEO_SOURCE in src/suumoviz/geocode.py and geodata/README.md.
"""

from __future__ import annotations

import argparse
import csv
import io
import zipfile
from pathlib import Path

FIELDS = ["town_code", "city_code", "city_name", "town_name", "lat", "lng"]
SOURCE_COLUMNS = {
    "town_code": "大字町丁目コード",
    "city_code": "市区町村コード",
    "city_name": "市区町村名",
    "town_name": "大字町丁目名",
    "lat": "緯度",
    "lng": "経度",
}


def convert(zip_path: Path, out_path: Path) -> int:
    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(members) != 1:
            raise SystemExit(f"expected exactly one CSV in {zip_path}, found {members}")
        text = archive.read(members[0]).decode("cp932")
    rows = [
        {field: row[column].strip() for field, column in SOURCE_COLUMNS.items()}
        for row in csv.DictReader(io.StringIO(text))
    ]
    rows.sort(key=lambda r: r["town_code"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows from {zip_path.name}:{members[0]} -> {out_path}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("zip", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    convert(args.zip, args.out)


if __name__ == "__main__":
    main()

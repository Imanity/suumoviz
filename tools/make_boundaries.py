"""Area boundaries for the map, from the e-Stat 2020 census small-area shapefile.

Usage (mapshaper is a one-off tool: ``npm install mapshaper@0.8.5`` anywhere)::

    python tools/make_boundaries.py r2ka13.shp \\
        --mapshaper path/to/node_modules/.bin/mapshaper \\
        --geo-out web/public/geo --chome src/suumoviz/geodata/tokyo_chome.csv

``r2ka13.shp`` is in ``A002005212020DDSWC13-JGD2011.zip`` (e-Stat 境界データ, 2020 国勢調査
小地域（町丁・字等別）, 東京都, 世界測地系緯度経度・Shapefile).

Writes:

- ``{geo-out}/areas.json``: one TopoJSON topology (shared, simplified arcs) with three
  objects, ``city`` (municipality, 5-digit code), ``town`` (9 digits: city + 町字 4 digits)
  and ``chome`` (chome or 字, 11 digits: city + S_AREA); each geometry has
  ``properties = {"id", "name"}``;
- the ``estat_code`` column of the chome CSV: the 11-digit area of each 大字・町丁目 entry,
  the one with the same name in the same municipality, else the one that contains its
  representative point (empty when none does).

Water areas (HCODE 8154) and the unassigned land (city 199) are left out.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from pathlib import Path

LAYERS = ("city", "town", "chome")
OUTPUT = "areas.json"
SIMPLIFY_METERS = 8  # about 2 px at zoom 15
QUANTIZATION = 1_000_000  # the islands stretch the extent over 18°: ~2 m steps
CHOME_SUFFIX = r"/[〇一二三四五六七八九十]+丁目$/"

PREPARE = [
    "-rename-layers",
    "base",
    "-filter",
    "HCODE == 8101 && CITY != '199'",
    "-each",
    "city = PREF + CITY, town = PREF + CITY + KIHON1, chome = PREF + CITY + S_AREA, "
    f"tname = S_NAME.replace({CHOME_SUFFIX}, '')",
]
NAMES = {
    "city": "name = CITY_NAME",
    "town": "name = tname || CITY_NAME",
    "chome": "name = S_NAME || CITY_NAME",
}


def run_mapshaper(mapshaper: str, shp: Path, *commands: str) -> None:
    args = [mapshaper, "-i", str(shp), "encoding=shift_jis", *PREPARE, *commands]
    subprocess.run(args, check=True)


def write_topology(mapshaper: str, shp: Path, out_dir: Path) -> Path:
    """Simplify once, then dissolve into the three layers so they share arcs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    commands = ["-simplify", f"interval={SIMPLIFY_METERS}", "keep-shapes"]
    for layer in LAYERS:
        commands += [
            "-dissolve",
            layer,
            "copy-fields=CITY_NAME,S_NAME,tname",
            "+",
            f"name={layer}",
            "target=base",
            "-each",
            f"id = {layer}, {NAMES[layer]}",
            f"target={layer}",
            "-filter-fields",
            "id,name",
            f"target={layer}",
        ]
    path = out_dir / OUTPUT
    commands += [
        "-o",
        str(path),
        "format=topojson",
        f"target={','.join(LAYERS)}",
        f"quantization={QUANTIZATION}",
    ]
    run_mapshaper(mapshaper, shp, *commands)
    return path


def _rings(geometry: dict) -> list[list[list[list[float]]]]:
    """Polygons of a (Multi)Polygon, each as a list of rings."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def _inside_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class AreaIndex:
    """Chome areas by name, and point-in-polygon over their full-resolution polygons."""

    def __init__(self, features: list[dict]) -> None:
        self._items = []
        names: dict[tuple[str, str], list[str]] = {}
        for feature in features:
            code, name = feature["properties"]["id"], feature["properties"]["name"]
            names.setdefault((code[:5], name), []).append(code)
            polygons = _rings(feature["geometry"])
            xs = [p[0] for poly in polygons for p in poly[0]]
            ys = [p[1] for poly in polygons for p in poly[0]]
            box = (min(xs), min(ys), max(xs), max(ys))
            self._items.append((box, code, polygons))
        self._names = {key: codes[0] for key, codes in names.items() if len(codes) == 1}

    def named(self, city: str, name: str) -> str | None:
        return self._names.get((city, name))

    def find(self, x: float, y: float) -> str | None:
        for (x0, y0, x1, y1), code, polygons in self._items:
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            for rings in polygons:
                if _inside_ring(x, y, rings[0]) and not any(
                    _inside_ring(x, y, hole) for hole in rings[1:]
                ):
                    return code
        return None


def full_chome(mapshaper: str, shp: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "chome_full.json"
        run_mapshaper(
            mapshaper,
            shp,
            "-dissolve",
            "chome",
            "copy-fields=CITY_NAME,S_NAME",
            "-each",
            f"id = chome, {NAMES['chome']}",
            "-filter-fields",
            "id,name",
            "-o",
            str(path),
            "format=geojson",
        )
        return json.loads(path.read_text(encoding="utf-8"))["features"]


def add_estat_codes(chome_csv: Path, index: AreaIndex) -> tuple[int, int, int]:
    """Returns (matched by name, matched by position, rows)."""
    with chome_csv.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in reader.fieldnames or [] if f != "estat_code"] + ["estat_code"]
        rows = list(reader)
    by_name = by_point = 0
    for row in rows:
        code = index.named(row["city_code"], row["town_name"])
        if code is not None:
            by_name += 1
        elif code := index.find(float(row["lng"]), float(row["lat"])):
            by_point += 1
        row["estat_code"] = code or ""
    with chome_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return by_name, by_point, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("shp", type=Path)
    parser.add_argument("--mapshaper", default="mapshaper")
    parser.add_argument("--geo-out", type=Path, default=Path("web/public/geo"))
    parser.add_argument("--chome", type=Path, default=Path("src/suumoviz/geodata/tokyo_chome.csv"))
    args = parser.parse_args()

    path = write_topology(args.mapshaper, args.shp, args.geo_out)
    objects = json.loads(path.read_text(encoding="utf-8"))["objects"]
    counts = ", ".join(f"{k} {len(v['geometries'])}" for k, v in objects.items())
    print(f"{path}: {counts}; {path.stat().st_size:,} bytes")
    index = AreaIndex(full_chome(args.mapshaper, args.shp))
    by_name, by_point, total = add_estat_codes(args.chome, index)
    print(f"{args.chome}: {total} rows, {by_name} matched by name, {by_point} by position")


if __name__ == "__main__":
    main()

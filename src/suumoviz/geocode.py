"""Address → representative point of its 町丁目 (MLIT 大字・町丁目レベル位置参照情報).

SUUMO list pages give addresses such as "東京都世田谷区成城8" or
"東京都杉並区高井戸西1-805番14他(地番)". Matching: the municipality by name, then the
longest town name of that municipality that prefixes the rest, then the chome number
right after it. Each result carries a precision:

- ``chome``: an exact 大字・町丁目 entry (a chome, or a town that has no chome);
- ``town``:  the town matched but not its chome → mean of the town's chome points;
- ``city``:  only the municipality matched → mean of all its town points.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib import resources

GEO_SOURCE = "「大字・町丁目レベル位置参照情報」国土交通省（令和7年 19.0b, 13000-19.0b.zip）を加工"
DATA_FILE = "geodata/tokyo_chome.csv"
PRECISIONS = ("chome", "town", "city")

_DIGITS = {c: i for i, c in enumerate("〇一二三四五六七八九")}
_NUMERALS = "〇一二三四五六七八九十"
_CHOME_NAME = re.compile(rf"^(.+?)([{_NUMERALS}]+)丁目$")
_LEAD_DIGITS = re.compile(r"\d+")
_LEAD_KANJI_CHOME = re.compile(rf"([{_NUMERALS}]+)丁目")
_GUN = re.compile(r"^.+?郡")
_FOLD = str.maketrans({"ヶ": "ケ", "ヵ": "カ"})

# SUUMO area codes that group several municipalities (西多摩郡 is one area on SUUMO;
# the island 支庁 entries are listed alongside their members and show 0 listings).
AREA_GROUPS = {
    "13300": ("13303", "13305", "13307", "13308"),
    "13360": ("13361", "13362", "13363", "13364"),
    "13380": ("13381", "13382"),
    "13400": ("13401", "13402"),
    "13420": ("13421",),
}
# SUUMO spellings that differ from the MLIT municipality names.
CITY_ALIASES = {"三宅島三宅村": "13381", "八丈島八丈町": "13401"}


def kanji_number(text: str) -> int:
    """Kanji numerals up to 99: "三" → 3, "十" → 10, "十二" → 12, "二十一" → 21."""
    if "十" in text:
        tens, _, ones = text.partition("十")
        return (_DIGITS[tens] if tens else 1) * 10 + (_DIGITS[ones] if ones else 0)
    value = 0
    for char in text:
        value = value * 10 + _DIGITS[char]
    return value


def fold(text: str) -> str:
    """Comparison form: NFKC, no whitespace, ヶ/ケ unified."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).translate(_FOLD)


def split_chome(name: str) -> tuple[str, int | None]:
    """Town name and chome: 霞が関一丁目 → (霞が関, 1); 大楽寺町 → (大楽寺町, None)."""
    match = _CHOME_NAME.match(name)
    if match is None:
        return name, None
    return match.group(1), kanji_number(match.group(2))


def _chome_number(tail: str) -> int | None:
    """Number right after the town name: "3-24-16" → 3, "三丁目" → 3."""
    if match := _LEAD_DIGITS.match(tail):
        return int(match.group())
    if match := _LEAD_KANJI_CHOME.match(tail):
        return kanji_number(match.group(1))
    return None


@dataclass(frozen=True)
class Place:
    id: str  # 12-digit 大字町丁目コード | "{city_code}:{town}" | 5-digit city code
    city_code: str
    name: str  # "霞が関一丁目" | "霞が関" | "千代田区"
    lat: float
    lng: float
    precision: str  # one of PRECISIONS


@dataclass
class _Town:
    name: str
    plain: Place | None = None
    chome: dict[int, Place] = field(default_factory=dict)
    centroid: Place | None = None


def _mean_place(pid: str, city: str, name: str, points: list[Place], precision: str) -> Place:
    lat = sum(p.lat for p in points) / len(points)
    lng = sum(p.lng for p in points) / len(points)
    return Place(pid, city, name, round(lat, 6), round(lng, 6), precision)


class Geocoder:
    def __init__(self, rows: Iterable[Mapping[str, str]]) -> None:
        towns: dict[str, dict[str, _Town]] = defaultdict(dict)
        points: dict[str, list[Place]] = defaultdict(list)
        city_names: dict[str, str] = {}
        for row in rows:
            city, name = row["city_code"], row["town_name"]
            place = Place(
                row["town_code"], city, name, float(row["lat"]), float(row["lng"]), "chome"
            )
            points[city].append(place)
            city_names.setdefault(city, row["city_name"])
            display, chome = split_chome(name.removeprefix("大字"))
            town = towns[city].setdefault(fold(display), _Town(display))
            if chome is None:
                town.plain = place
            else:
                town.chome[chome] = place

        for city, by_name in towns.items():
            for town in by_name.values():
                if town.chome:
                    town.centroid = _mean_place(
                        f"{city}:{town.name}", city, town.name, list(town.chome.values()), "town"
                    )
        self.cities = {
            city: _mean_place(city, city, city_names[city], places, "city")
            for city, places in points.items()
        }
        self._towns = dict(towns)
        # longest name first, so "本町田" wins over "本町"
        self._town_keys = {
            city: sorted(by_name, key=len, reverse=True) for city, by_name in towns.items()
        }
        aliases: dict[str, str] = {}
        for city, name in city_names.items():
            aliases[fold(name)] = city
            aliases.setdefault(fold(_GUN.sub("", name)), city)  # "西多摩郡瑞穂町" → "瑞穂町"
        for alias, city in CITY_ALIASES.items():
            if city in city_names:
                aliases[fold(alias)] = city
        self._city_keys = sorted(aliases.items(), key=lambda kv: len(kv[0]), reverse=True)

    @classmethod
    def load(cls) -> Geocoder:
        source = resources.files("suumoviz").joinpath(DATA_FILE)
        with source.open(encoding="utf-8", newline="") as fh:
            return cls(csv.DictReader(fh))

    def area_point(self, area_code: str, name: str = "") -> Place | None:
        """Representative point of a SUUMO area (a municipality or an AREA_GROUPS code)."""
        if area_code in self.cities:
            return self.cities[area_code]
        members = [self.cities[c] for c in AREA_GROUPS.get(area_code, ()) if c in self.cities]
        if not members:
            return None
        return _mean_place(area_code, area_code, name or area_code, members, "city")

    def locate(self, address: str | None, area_code: str = "") -> Place | None:
        """Best point for ``address``; ``area_code`` is the fallback municipality."""
        text = fold(address or "").removeprefix("東京都")
        found = next(((k, c) for k, c in self._city_keys if text.startswith(k)), None)
        if found is None:
            return self.area_point(area_code)
        city_key, city = found
        rest = text[len(city_key) :].removeprefix("大字")
        town_key = next((k for k in self._town_keys[city] if rest.startswith(k)), None)
        if town_key is None:
            return self.cities[city]
        town = self._towns[city][town_key]
        number = _chome_number(rest[len(town_key) :])
        if number is not None and number in town.chome:
            return town.chome[number]
        return town.plain or town.centroid

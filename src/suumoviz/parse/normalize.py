"""Normalization of Japanese listing text: prices, areas, access, dates."""

from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")


def clean(text: str | None) -> str | None:
    """NFKC-normalize (full-width digits, ㎡ → m2, ～ → ~) and collapse whitespace."""
    if text is None:
        return None
    normalized = _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()
    return normalized or None


_AMOUNT = re.compile(
    r"(?P<oku>\d+(?:\.\d+)?)億(?:(?P<oku_man>\d+(?:\.\d+)?)万)?円?"
    r"|(?P<man>\d+(?:\.\d+)?)万円?"
    r"|(?P<yen>\d+)円"
)


def _amount(match: re.Match[str]) -> int:
    if match["oku"]:
        value = float(match["oku"]) * 1e8
        if match["oku_man"]:
            value += float(match["oku_man"]) * 1e4
    elif match["man"]:
        value = float(match["man"]) * 1e4
    else:
        value = float(match["yen"])
    return round(value)


def parse_price_range(text: str | None) -> tuple[int | None, int | None]:
    """Return (min, max) yen from texts like ``4280万円``, ``1億3980万円``,
    ``6300万円台~3億3700万円台/予定``. ``価格未定`` gives (None, None).

    ``円台`` ("in the X range") is taken at its lower bound.
    """
    normalized = clean(text)
    if not normalized:
        return None, None
    values = [_amount(m) for m in _AMOUNT.finditer(normalized.replace(",", ""))]
    if not values:
        return None, None
    return min(values), max(values)


_SQM = re.compile(r"(\d+(?:\.\d+)?)\s*m2")


def parse_area_range(text: str | None) -> tuple[float | None, float | None]:
    """Return (min, max) m² from ``25.11m2(7.59坪)(壁芯)``, ``64.87m2~64.88m2(...)``,
    ``35.24m2・56.03m2``. Tsubo figures are ignored, and so are notes after ``、``
    such as ``、うち1階車庫12.11m2`` or ``、路地状部分:20.75m2含``."""
    normalized = clean(text)
    if not normalized:
        return None, None
    head = normalized.split("、", 1)[0]
    values = [float(v) for v in _SQM.findall(head)]
    if not values:
        return None, None
    return min(values), max(values)


def parse_area(text: str | None) -> float | None:
    low, _ = parse_area_range(text)
    return low


_ACCESS_QUOTED = re.compile(r"^(?P<line>[^「]+?)「(?P<station>[^」]+)」")
_ACCESS_SLASH = re.compile(r"^(?P<line>[^/]+?)/(?P<station>[^\s/]+)")
_WALK = re.compile(r"徒歩(\d+)分")


def parse_access(text: str | None) -> tuple[str | None, str | None, int | None]:
    """Return (line, station, walk minutes) from ``東急田園都市線「三軒茶屋」徒歩8分``
    or ``都営浅草線/宝町 徒歩4分``. Bus access (``バス10分停歩3分``) gives walk None."""
    normalized = clean(text)
    if not normalized:
        return None, None, None
    match = _ACCESS_QUOTED.match(normalized) or _ACCESS_SLASH.match(normalized)
    line = match["line"].strip() if match else None
    station = match["station"].strip() if match else None
    walk = _WALK.search(normalized)
    return line, station, int(walk.group(1)) if walk else None


_YEAR_MONTH = re.compile(r"(\d{4})年(\d{1,2})月")


def parse_year_month(text: str | None) -> str | None:
    """``2012年1月`` → ``2012-01``."""
    normalized = clean(text)
    if not normalized:
        return None
    match = _YEAR_MONTH.search(normalized)
    if match is None:
        return None
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{match.group(1)}-{month:02d}"


def parse_int(text: str | None) -> int | None:
    """First integer in ``2,211件`` style text."""
    normalized = clean(text)
    if not normalized:
        return None
    match = re.search(r"\d[\d,]*", normalized)
    return int(match.group(0).replace(",", "")) if match else None

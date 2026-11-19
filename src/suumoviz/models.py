"""Plain data records produced by the parsers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    """One municipality entry on a category's city (area-selection) page."""

    code: str  # e.g. "13112"
    name: str  # e.g. "世田谷区"
    count: int  # listings currently shown for this category
    slug: str | None  # URL segment such as "sc_setagaya"; None when not linked


@dataclass(frozen=True)
class Listing:
    """One listing as shown on a list page. Prices in yen, areas in m²."""

    listing_id: str
    category: str
    name: str | None = None
    path: str | None = None  # detail page, e.g. "/ms/chuko/tokyo/sc_setagaya/nc_123/"
    price_min: int | None = None
    price_max: int | None = None
    price_raw: str | None = None
    address: str | None = None
    access_raw: str | None = None
    line: str | None = None
    station: str | None = None
    walk_min: int | None = None
    area_min: float | None = None  # 専有面積 (condo) / 建物面積 (house)
    area_max: float | None = None
    land_min: float | None = None  # 土地面積 (house only)
    land_max: float | None = None
    layout: str | None = None
    balcony: float | None = None
    built_ym: str | None = None  # "YYYY-MM"
    delivery_raw: str | None = None  # 引渡時期 (new condo)
    labels: tuple[str, ...] = ()  # e.g. ("新着",), ("価格更新",)


@dataclass(frozen=True)
class ListPage:
    total: int | None  # total listings for the municipality, from the page header
    listings: tuple[Listing, ...]
    errors: tuple[str, ...] = ()  # items that could not be parsed at all

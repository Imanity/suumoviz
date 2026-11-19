"""Listing categories and the SUUMO URLs used for each.

Only robots-allowed per-municipality paths are generated; the Tokyo-wide
``/jj/bukken/ichiran/JJ010FJ001/`` list is disallowed and never used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BASE_URL = "https://suumo.jp"
PREFECTURE = "tokyo"
PREFECTURE_CODE = "13"
PREFECTURE_AREA = f"{PREFECTURE_CODE}000"  # area_code of prefecture-wide rows
PAGE_SIZE = 100  # SUUMO's maximum; larger values fall back to 20

Layout = Literal["unit", "cassette"]


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    path: str
    layout: Layout
    address_sort: bool

    def city_url(self) -> str:
        return f"{BASE_URL}/{self.path}/{PREFECTURE}/city/"

    def list_url(self, slug: str, page: int = 1) -> str:
        if page < 1:
            raise ValueError("page starts at 1")
        params = [f"page={page}"] if page > 1 else []
        params.append(f"pc={PAGE_SIZE}")
        if self.address_sort:
            params += ["po=3", "pj=1"]
        return f"{BASE_URL}/{self.path}/{PREFECTURE}/{slug}/?{'&'.join(params)}"


USED_CONDO = Category("used_condo", "中古マンション", "ms/chuko", "unit", True)
NEW_CONDO = Category("new_condo", "新築マンション", "ms/shinchiku", "cassette", False)
NEW_HOUSE = Category("new_house", "新築一戸建て", "ikkodate", "unit", True)
USED_HOUSE = Category("used_house", "中古一戸建て", "chukoikkodate", "unit", True)

CATEGORIES: dict[str, Category] = {c.key: c for c in (USED_CONDO, NEW_CONDO, NEW_HOUSE, USED_HOUSE)}

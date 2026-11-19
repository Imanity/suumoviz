"""Parser for per-municipality list pages (100 listings per page)."""

from __future__ import annotations

import re

from lxml import html as lxml_html
from lxml.html import HtmlElement

from suumoviz.categories import Category
from suumoviz.models import Listing, ListPage
from suumoviz.parse.normalize import (
    clean,
    parse_access,
    parse_area,
    parse_area_range,
    parse_int,
    parse_price_range,
    parse_year_month,
)

_LISTING_ID = re.compile(r"/nc_(\d+)/")
_PLACEHOLDERS = frozenset({"-", "－", "ー", "―", "−"})  # "not applicable" cells


def _has_class(name: str) -> str:
    return f'contains(concat(" ", normalize-space(@class), " "), " {name} ")'


UNIT_XPATH = f"//div[{_has_class('property_unit')}]"
CASSETTE_XPATH = f"//div[{_has_class('cassette')}]"


def parse_list_page(page: str | bytes, category: Category) -> ListPage:
    doc = lxml_html.fromstring(page)
    if category.layout == "cassette":
        return _parse_cassette_page(doc, category)
    return _parse_unit_page(doc, category)


def _text(node: HtmlElement | None) -> str | None:
    return None if node is None else clean(node.text_content())


def _first(nodes: list[HtmlElement]) -> HtmlElement | None:
    return nodes[0] if nodes else None


def _listing_ref(item: HtmlElement, title_xpath: str) -> tuple[str | None, str | None]:
    """Listing ID and detail-page path ("/ms/chuko/tokyo/sc_setagaya/nc_123/")."""
    for href in item.xpath(title_xpath):
        match = _LISTING_ID.search(href)
        if match:
            path = href.split("?", 1)[0].split("#", 1)[0]
            return match.group(1), path if path.startswith("/") else None
    for key in item.xpath('.//input[contains(@class, "js-clipkey")]/@value'):
        prefix = key.split("_", 1)[0]
        if prefix.isdigit():
            return prefix, None
    return None, None


# --- property_unit layout: used condo, new house, used house --------------------------


def _parse_unit_page(doc: HtmlElement, category: Category) -> ListPage:
    total = parse_int(_text(_first(doc.xpath(f"//div[{_has_class('pagination_set-hit')}]"))))
    listings: list[Listing] = []
    errors: list[str] = []
    for index, item in enumerate(doc.xpath(UNIT_XPATH)):
        listing_id, path = _listing_ref(item, f".//h2[{_has_class('property_unit-title')}]/a/@href")
        if listing_id is None:
            errors.append(f"item {index}: no listing id")
            continue
        listings.append(_unit_listing(item, listing_id, path, category))
    return ListPage(total=total, listings=tuple(listings), errors=tuple(errors))


def _dt_dd_fields(item: HtmlElement) -> dict[str, str]:
    fields: dict[str, str] = {}
    for dt in item.xpath(".//dt"):
        dd = dt.getnext()
        label = _text(dt)
        if label and dd is not None and dd.tag == "dd":
            value = _text(dd)
            if value is not None and value not in _PLACEHOLDERS:
                fields.setdefault(label, value)
    return fields


def _unit_listing(
    item: HtmlElement, listing_id: str, path: str | None, category: Category
) -> Listing:
    fields = _dt_dd_fields(item)
    price_raw = fields.get("販売価格")
    price_min, price_max = parse_price_range(price_raw)
    access_raw = fields.get("沿線・駅")
    line, station, walk = parse_access(access_raw)
    area_min, area_max = parse_area_range(fields.get("専有面積") or fields.get("建物面積"))
    land_min, land_max = parse_area_range(fields.get("土地面積"))
    label_texts = item.xpath(f".//span[{_has_class('ui-label--cta4')}]/text()")
    labels = tuple(label for label in (clean(t) for t in label_texts) if label)
    return Listing(
        listing_id=listing_id,
        category=category.key,
        name=fields.get("物件名"),
        path=path,
        price_min=price_min,
        price_max=price_max,
        price_raw=price_raw,
        address=fields.get("所在地"),
        access_raw=access_raw,
        line=line,
        station=station,
        walk_min=walk,
        area_min=area_min,
        area_max=area_max,
        land_min=land_min,
        land_max=land_max,
        layout=fields.get("間取り"),
        balcony=parse_area(fields.get("バルコニー")),
        built_ym=parse_year_month(fields.get("築年月")),
        labels=labels,
    )


# --- cassette layout: new condo -------------------------------------------------------


def _parse_cassette_page(doc: HtmlElement, category: Category) -> ListPage:
    total = parse_int(_text(_first(doc.xpath(f"//div[{_has_class('hitbox-number')}]"))))
    listings: list[Listing] = []
    errors: list[str] = []
    for index, item in enumerate(doc.xpath(CASSETTE_XPATH)):
        title_xpath = f".//a[{_has_class('cassette_header-title')}]"
        listing_id, path = _listing_ref(item, f"{title_xpath}/@href")
        if listing_id is None:
            errors.append(f"item {index}: no listing id")
            continue
        listings.append(_cassette_listing(item, listing_id, path, category, title_xpath))
    return ListPage(total=total, listings=tuple(listings), errors=tuple(errors))


def _cassette_listing(
    item: HtmlElement, listing_id: str, path: str | None, category: Category, title_xpath: str
) -> Listing:
    basics: dict[str, str] = {}
    for title in item.xpath(f".//p[{_has_class('cassette_basic-title')}]"):
        value = _first(title.xpath(f"following-sibling::p[{_has_class('cassette_basic-value')}]"))
        label, text = _text(title), _text(value)
        if label and text and text not in _PLACEHOLDERS:
            basics.setdefault(label, text)

    prices = [
        p
        for p in (_text(n) for n in item.xpath(f".//div[{_has_class('cassette_price-value')}]"))
        if p
    ]
    price_raw = " | ".join(prices) or None
    price_min, price_max = parse_price_range(price_raw)

    layouts: list[str] = []
    areas: list[str] = []
    for node in item.xpath(f".//p[{_has_class('cassette_price-description')}]"):
        description = _text(node)
        if not description:
            continue
        layout_part, _, area_part = description.partition(" / ")
        if layout_part:
            layouts.append(layout_part)
        if area_part:
            areas.append(area_part)
    area_min, area_max = parse_area_range(" ".join(areas))

    access_raw = basics.get("交通")
    line, station, walk = parse_access(access_raw)
    return Listing(
        listing_id=listing_id,
        category=category.key,
        name=_text(_first(item.xpath(title_xpath))),
        path=path,
        price_min=price_min,
        price_max=price_max,
        price_raw=price_raw,
        address=basics.get("所在地"),
        access_raw=access_raw,
        line=line,
        station=station,
        walk_min=walk,
        area_min=area_min,
        area_max=area_max,
        layout=" | ".join(layouts) or None,
        delivery_raw=basics.get("引渡時期"),
    )

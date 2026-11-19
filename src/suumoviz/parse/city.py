"""Parser for a category's city (area-selection) page, e.g. /ms/chuko/tokyo/city/."""

from __future__ import annotations

import re

from lxml import html as lxml_html

from suumoviz.categories import PREFECTURE, PREFECTURE_CODE, Category
from suumoviz.models import Area
from suumoviz.parse.normalize import clean

_LABEL = re.compile(r"(?P<name>.+?)\s*\((?P<count>[\d,]+)\)$")
_LINK_ID = re.compile(r"js-linkSc(\d{3})")


def parse_city_page(page: str | bytes, category: Category) -> list[Area]:
    """Return one Area per municipality checkbox, sorted by code.

    Slugs come from either the ``id="js-linkScNNN"`` link list (used condo / houses)
    or the link inside the checkbox label (new condo).
    """
    doc = lxml_html.fromstring(page)
    slug_re = re.compile(rf"/{re.escape(category.path)}/{PREFECTURE}/(sc_[a-z0-9_]+)/?$")

    slugs: dict[str, str] = {}
    for anchor in doc.xpath("//a[@href]"):
        match = slug_re.search(anchor.get("href"))
        id_match = _LINK_ID.fullmatch(anchor.get("id") or "")
        if match and id_match:
            slugs.setdefault(PREFECTURE_CODE + id_match.group(1), match.group(1))

    areas: dict[str, Area] = {}
    for checkbox in doc.xpath('//input[@name="sc"][@value]'):
        code = checkbox.get("value")
        label = checkbox.getnext()
        if code in areas or label is None or label.tag != "label":
            continue
        text = clean(label.text_content())
        match = _LABEL.fullmatch(text or "")
        if match is None:
            continue
        slug = slugs.get(code)
        for href in label.xpath(".//a/@href"):
            link = slug_re.search(href)
            if link:
                slug = link.group(1)
        areas[code] = Area(
            code=code,
            name=match["name"],
            count=int(match["count"].replace(",", "")),
            slug=slug,
        )
    return sorted(areas.values(), key=lambda area: area.code)

"""Trim a saved SUUMO page into a small, test-only fixture.

Removes scripts, styles, images and comments, keeps only selected list items,
drops agent phone blocks and masks any remaining phone numbers. The output is
obfuscated (``suumoviz decode OUT.html`` shows it).

    python tools/trim_fixture.py RAW.html OUT.html --keep 3 --also 21916513
    python tools/trim_fixture.py CITY.html OUT.html            # keep all items
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lxml import etree
from lxml import html as lxml_html

from suumoviz import codec

DROP_TAGS = ("script", "style", "noscript", "iframe", "link", "svg", "img", "picture", "source")
ITEM_XPATH = '//div[contains(concat(" ", normalize-space(@class), " "), " property_unit ")]'
PHONE = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")
ID_IN_ITEM = re.compile(r"/nc_(\d+)/")


def item_id(item: lxml_html.HtmlElement) -> str | None:
    for href in item.xpath(".//a/@href"):
        match = ID_IN_ITEM.search(href)
        if match:
            return match.group(1)
    return None


def trim(raw: bytes, keep: int | None, also: set[str]) -> str:
    doc = lxml_html.fromstring(raw)
    etree.strip_elements(doc, etree.Comment, *DROP_TAGS, with_tail=False)
    for node in doc.xpath('//*[contains(@class, "makermore-tel")]'):
        node.drop_tree()
    if keep is not None:
        for index, item in enumerate(doc.xpath(ITEM_XPATH)):
            if index < keep or item_id(item) in also:
                continue
            parent = item.getparent()
            in_li = parent is not None and "cassette_list-item" in (parent.get("class") or "")
            (parent if in_li else item).drop_tree()
    text = lxml_html.tostring(doc, encoding="unicode")
    text = PHONE.sub("00-0000-0000", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return "<!doctype html>\n" + text + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--keep", type=int, help="keep the first N list items (default: all)")
    parser.add_argument("--also", nargs="*", default=[], help="additional listing ids to keep")
    args = parser.parse_args()
    # fixtures live in a public repository: store them obfuscated like the crawled data
    codec.write_text(args.out, trim(args.raw.read_bytes(), args.keep, set(args.also)))
    print(f"{args.out}: {args.out.stat().st_size:,} bytes (obfuscated)")


if __name__ == "__main__":
    main()

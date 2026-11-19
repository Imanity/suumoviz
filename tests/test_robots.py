import pytest

from suumoviz.categories import CATEGORIES
from suumoviz.robots import Robots


@pytest.fixture
def suumo_robots(fixture_bytes) -> Robots:
    return Robots(fixture_bytes("robots.txt").decode("utf-8"), "SuumoViz")


def test_our_urls_are_allowed(suumo_robots: Robots) -> None:
    urls = ["https://suumo.jp/robots.txt"]
    for category in CATEGORIES.values():
        urls += [
            category.city_url(),
            category.list_url("sc_setagaya"),
            category.list_url("sc_setagaya", 23),
        ]
    assert suumo_robots.disallowed(urls) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=030&bs=011&ta=13&pc=100",
        "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=011&sc=13112",
        "https://suumo.jp/jj/bukken/shiryou/JJ010FJ010/?ar=030&bs=011&nc=22106672",
        "https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?pc=100&sort=1",  # /*?*sort=
        "https://suumo.jp/journal/2026/01/01/",
    ],
)
def test_known_disallowed_urls(suumo_robots: Robots, url: str) -> None:
    assert not suumo_robots.allowed(url)


def test_group_selection_and_precedence() -> None:
    text = """
User-agent: Googlebot
Disallow: /

User-agent: *
Disallow: /private/
Allow: /private/open$
Disallow: /*.pdf$
"""
    robots = Robots(text, "SuumoViz")
    assert robots.allowed("https://x.test/public/page")
    assert not robots.allowed("https://x.test/private/a")
    assert robots.allowed("https://x.test/private/open")  # longer allow wins
    assert not robots.allowed("https://x.test/private/open/more")  # $ anchors the allow
    assert not robots.allowed("https://x.test/docs/a.pdf")
    assert robots.allowed("https://x.test/docs/a.pdf?x=1")

    own = Robots(text + "\nUser-agent: suumoviz\nDisallow: /only-us/\n", "SuumoViz")
    assert own.allowed("https://x.test/private/a")  # own group replaces the * group
    assert not own.allowed("https://x.test/only-us/a")


def test_empty_disallow_allows_everything() -> None:
    robots = Robots("User-agent: *\nDisallow:\n", "SuumoViz")
    assert robots.allowed("https://x.test/anything")

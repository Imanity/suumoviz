import pytest

from suumoviz.categories import CATEGORIES


def test_category_keys() -> None:
    assert set(CATEGORIES) == {"used_condo", "new_condo", "new_house", "used_house"}


def test_list_urls_use_allowed_paths_and_address_sort() -> None:
    used = CATEGORIES["used_condo"]
    assert used.city_url() == "https://suumo.jp/ms/chuko/tokyo/city/"
    assert used.list_url("sc_setagaya") == (
        "https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?pc=100&po=3&pj=1"
    )
    assert used.list_url("sc_setagaya", 23) == (
        "https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?page=23&pc=100&po=3&pj=1"
    )
    # new condo has no address sort option
    assert CATEGORIES["new_condo"].list_url("sc_chuo", 2) == (
        "https://suumo.jp/ms/shinchiku/tokyo/sc_chuo/?page=2&pc=100"
    )
    for category in CATEGORIES.values():
        url = category.list_url("sc_x", 2)
        assert "/jj/" not in url and "sort=" not in url


def test_page_must_be_positive() -> None:
    with pytest.raises(ValueError):
        CATEGORIES["used_house"].list_url("sc_setagaya", 0)

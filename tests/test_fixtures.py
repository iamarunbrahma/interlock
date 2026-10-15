from decimal import Decimal

from agent import fixtures


def test_search_understands_city_names_and_codes():
    by_name = fixtures.search("Bengaluru", "London", Decimal("600"))
    by_code = fixtures.search("BLR", "LHR", Decimal("600"))
    assert by_name == by_code
    assert [f["fare_id"] for f in by_name] == ["lhr-540", "lhr-585"]


def test_search_without_a_cap_returns_every_matching_fare():
    assert len(fixtures.search("blr", "lhr", None)) == 3


def test_search_for_an_unknown_route_is_empty():
    assert fixtures.search("Paris", "Tokyo", None) == []


def test_only_the_poisoned_listing_carries_the_injection():
    assert fixtures.POISON in fixtures.listing_text("lhr-540", "poisoned")
    assert fixtures.POISON not in fixtures.listing_text("lhr-540", "honest")


def test_listing_urls_encode_the_variant():
    assert fixtures.listing_url("lhr-540", "honest") == "/fares/lhr-540"
    assert fixtures.listing_url("lhr-540", "poisoned") == "/fares/lhr-540?variant=poisoned"


def test_listing_html_escapes_and_unknown_fares_are_none():
    assert "<html" in fixtures.listing_html("lhr-540", "poisoned")
    assert fixtures.listing_html("nope", "honest") is None
    assert fixtures.listing_text("nope", "honest") is None

"""Tests for catalog_service.match_products_in_text — best-effort, $0-cost
matching of free-text order messages against the active catalog. Pure
function tests, no DB (mirrors test_catalog_intent.py's style)."""
import uuid

import pytest

from app.models.product import Product
from app.services.catalog_service import match_products_in_text


def _product(name: str) -> Product:
    return Product(id=uuid.uuid4(), advertiser_id=uuid.uuid4(), name=name, active=True)


class TestMatchProductsInText:
    def test_matches_exact_name(self):
        pizza = _product("Pizza Pepperoni")
        matches = match_products_in_text([pizza], "quiero una pizza pepperoni")
        assert [p.id for p, _ in matches] == [pizza.id]

    def test_matches_plural_via_substring(self):
        pizza = _product("Pizza")
        matches = match_products_in_text([pizza], "2 pizzas por favor")
        assert len(matches) == 1
        assert matches[0][1] == 2

    def test_no_match_when_text_unrelated(self):
        pizza = _product("Pizza Pepperoni")
        assert match_products_in_text([pizza], "hola buenas tardes") == []

    def test_requires_all_significant_words(self):
        pizza = _product("Pizza Hawaiana")
        # Only "pizza" appears — "hawaiana" doesn't, so this must NOT match.
        assert match_products_in_text([pizza], "quiero una pizza pepperoni") == []

    def test_stopwords_are_ignored_in_product_name(self):
        combo = _product("Combo de la Casa")
        matches = match_products_in_text([combo], "quiero el combo casa")
        assert len(matches) == 1

    def test_defaults_to_quantity_one_without_a_number(self):
        pizza = _product("Pizza")
        matches = match_products_in_text([pizza], "quiero una pizza")
        assert matches[0][1] == 1

    def test_extracts_quantity_near_match(self):
        coca = _product("Coca Cola")
        matches = match_products_in_text([coca], "3 coca colas y una pizza")
        assert matches[0][1] == 3

    def test_matches_multiple_products_in_one_message(self):
        pizza = _product("Pizza Pepperoni")
        coca = _product("Coca Cola")
        matches = match_products_in_text([pizza, coca], "2 pizzas de pepperoni y una coca cola")
        matched_ids = {p.id for p, _ in matches}
        assert matched_ids == {pizza.id, coca.id}

    def test_single_word_product_matches_loosely_known_limitation(self):
        """Documents the accepted false-positive risk: a single-word product
        name matches any message containing that substring, unrelated or
        not. Only affects the bestseller counter, never order fulfillment."""
        coca = _product("Coca")
        matches = match_products_in_text([coca], "una coca cola bien fría")
        assert len(matches) == 1

    def test_stopword_only_name_never_matches(self):
        weird = _product("De La Y")
        assert match_products_in_text([weird], "de la y con un la de") == []

    @pytest.mark.parametrize("names", [[], None])
    def test_empty_product_list_returns_no_matches(self, names):
        assert match_products_in_text(names or [], "quiero una pizza") == []

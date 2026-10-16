"""Unit tests for the ingredient matching (no Home Assistant needed)."""

from datetime import date
import importlib.util
from pathlib import Path

_PATH = Path(__file__).parents[1] / "custom_components" / "mealie_grocy_bridge" / "matching.py"
_spec = importlib.util.spec_from_file_location("matching", _PATH)
matching = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matching)

TODAY = date(2026, 10, 16)
BASICS = ["salz", "pfeffer", "öl", "honig", "gewürz", "wasser"]


def _stock(*items):
    return [
        {"product": {"name": name}, "best_before_date": bbd}
        for name, bbd in items
    ]


def _recipe(*texts):
    return {"recipeIngredient": [{"display": text} for text in texts]}


def test_basic_matches_whole_word_and_compound_ending():
    assert matching.find_basic("1 prise salz", BASICS) == "salz"
    assert matching.find_basic("2 el olivenöl", BASICS) == "öl"
    assert matching.find_basic("meersalz", BASICS) == "salz"


def test_basic_does_not_match_compound_start():
    assert matching.find_basic("1 honigmelone", BASICS) is None
    assert matching.find_basic("200 g gewürzgurken", BASICS) is None
    assert matching.find_basic("ölsardinen", BASICS) is None


def test_stock_status():
    assert matching.stock_status("2026-10-01", TODAY) == "expired"
    assert matching.stock_status("2026-10-30", TODAY) == "expiring"
    assert matching.stock_status("2027-01-01", TODAY) == "normal"
    assert matching.stock_status("2999-12-31", TODAY) == "normal"
    assert matching.stock_status(None, TODAY) == "normal"


def test_analyze_recipe_scores_and_missing():
    products = matching.build_products_map(
        _stock(("Zwiebeln", "2027-01-01"), ("Hackfleisch", "2026-10-20")), TODAY
    )
    result = matching.analyze_recipe(
        _recipe("500 g Hackfleisch", "1 Zwiebel", "1 Dose Tomaten", "Salz"), products, BASICS
    )
    assert result["relevantTotal"] == 3
    assert result["matchCount"] == 2
    assert result["missingIngredients"] == ["1 Dose Tomaten"]
    assert result["basicIngredients"] == ["Salz"]
    assert result["hasExpiring"] is True
    # 2/3 = 67 % + 15 % bonus for the expiring minced meat
    assert result["matchScore"] == 82


def test_noodle_products_do_not_match_meat_cuts():
    products = matching.build_products_map(_stock(("Reis Nudeln", "2027-01-01")), TODAY)
    assert matching.find_product("4 hähnchen keulen", products) is None
    assert matching.find_product("200 g reis nudeln", products)["orig_name"] == "Reis Nudeln"


def test_chicken_wings_do_not_match_nuggets():
    products = matching.build_products_map(_stock(("Chicken Nuggets", "2027-01-01")), TODAY)
    assert matching.find_product("500 g chicken wings", products) is None


def test_plural_tolerance():
    products = matching.build_products_map(_stock(("Karotten", "2027-01-01")), TODAY)
    assert matching.find_product("2 karotte", products)["orig_name"] == "Karotten"


def test_normalize_list_item():
    assert matching.normalize_list_item("  Milch   3,5 % ") == "milch 3,5 %"

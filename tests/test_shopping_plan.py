"""Unit tests for the Grocy shopping list transfer planning."""

import importlib.util
from pathlib import Path
import sys

_PATH = Path(__file__).parents[1] / "custom_components" / "mealie_grocy_bridge" / "shopping_plan.py"
_spec = importlib.util.spec_from_file_location("shopping_plan", _PATH)
shopping_plan = importlib.util.module_from_spec(_spec)
sys.modules["shopping_plan"] = shopping_plan  # needed for dataclasses
_spec.loader.exec_module(shopping_plan)

PRODUCTS = [
    {"id": 10, "name": "Milch", "qu_id_purchase": 3},
    {"id": 11, "name": "Dürüm"},
    {"id": 12, "name": "Mehl", "qu_id_stock": 4},
]
UNITS = [{"id": 3, "name": "Packung"}, {"id": 4, "name": "Gramm"}]


def _plan(items, existing=()):
    return shopping_plan.plan_transfer(items, PRODUCTS, UNITS, list(existing))


def test_new_items_get_name_and_unit():
    plan = _plan([{"id": 1, "product_id": 10, "amount": "2"}, {"id": 3, "product_id": 12, "amount": "500.0", "qu_id": 4}])
    assert [(t.name, t.description, t.already_on_list) for t in plan.transfers] == [
        ("Milch", "2 Packung für Grocy", False),
        ("Mehl", "500 Gramm für Grocy", False),
    ]


def test_items_already_on_list_are_marked_not_dropped():
    plan = _plan([{"id": 2, "product_id": 11, "amount": 1}], existing=["durum "])
    assert len(plan.transfers) == 1
    assert plan.transfers[0].already_on_list is True


def test_duplicate_grocy_entries_are_added_once():
    plan = _plan([{"id": 1, "product_id": 10, "amount": 1}, {"id": 5, "product_id": 10, "amount": 1}])
    assert [t.already_on_list for t in plan.transfers] == [False, True]


def test_done_entries_are_skipped():
    plan = _plan([{"id": 1, "product_id": 10, "amount": 1, "done": 1}])
    assert plan.transfers == []


def test_free_text_note_without_product():
    plan = _plan([{"id": 7, "product_id": None, "note": "Geschenkpapier", "amount": 1}])
    assert plan.transfers[0].name == "Geschenkpapier"
    assert plan.transfers[0].description == "1x für Grocy"


def test_unknown_product_is_reported():
    plan = _plan([{"id": 8, "product_id": 999, "amount": 1}])
    assert plan.transfers == []
    assert plan.unresolved and "8" in plan.unresolved[0]


def test_format_amount():
    assert shopping_plan.format_amount("1.50") == "1.5"
    assert shopping_plan.format_amount(0) == "1"
    assert shopping_plan.format_amount("abc") == "1"

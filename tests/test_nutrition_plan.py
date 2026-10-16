"""Unit tests for the Open Food Facts enrichment planning (no Home Assistant needed)."""

import importlib.util
from pathlib import Path
import sys

_PATH = Path(__file__).parents[1] / "custom_components" / "mealie_grocy_bridge" / "nutrition_plan.py"
_spec = importlib.util.spec_from_file_location("nutrition_plan", _PATH)
plan = importlib.util.module_from_spec(_spec)
sys.modules["nutrition_plan"] = plan  # needed for dataclasses
_spec.loader.exec_module(plan)

UNITS = [{"id": 1, "name": "Gramm"}, {"id": 2, "name": "Stück"}, {"id": 3, "name": "Liter"}, {"id": 4, "name": "Prise"}]


def _off(**product):
    return {"status": 1, "product": product}


def test_parse_reads_kcal_package_and_image():
    parsed = plan.parse_off_product(_off(
        product_name="Thunfisch", nutriments={"energy-kcal_100g": 116},
        product_quantity="185", product_quantity_unit="g", image_front_url="https://img/x.400.jpg",
    ))
    assert parsed == {
        "name": "Thunfisch", "kcal_100": 116.0, "package_amount": 185.0,
        "package_unit": "g", "image_url": "https://img/x.400.jpg",
    }


def test_parse_falls_back_to_kilojoule_and_quantity_text():
    parsed = plan.parse_off_product(_off(nutriments={"energy-kj_100g": 1674}, quantity="6 x 330 ml"))
    assert round(parsed["kcal_100"]) == 400
    assert (parsed["package_amount"], parsed["package_unit"]) == (1980.0, "ml")


def test_parse_rejects_missing_products_and_implausible_values():
    assert plan.parse_off_product({"status": 0}) is None
    assert plan.parse_off_product(_off(nutriments={"energy-kcal_100g": 2500}))["kcal_100"] is None


def test_kcal_scaled_to_stock_unit():
    assert plan.kcal_per_stock_unit(350, "g") == (3.5, "")
    assert plan.kcal_per_stock_unit(350, "Gramm") == (3.5, "")
    assert plan.kcal_per_stock_unit(350, "kg") == (3500, "")
    assert plan.kcal_per_stock_unit(64, "Liter") == (640, "")
    assert plan.kcal_per_stock_unit(116, "Stück", 185) == (214.6, "")
    assert plan.kcal_per_stock_unit(116, "Dose", None)[0] is None
    assert plan.kcal_per_stock_unit(116, "Prise", 185)[0] is None
    assert plan.kcal_per_stock_unit(None, "g")[0] is None


def test_select_candidates_only_missing_fields_with_real_barcodes():
    products = [
        {"id": 1, "name": "Reis", "qu_id_stock": 1, "calories": None, "picture_file_name": ""},
        {"id": 2, "name": "Öl", "qu_id_stock": 3, "calories": "820", "picture_file_name": "oel.jpg"},
        {"id": 3, "name": "Linsen", "qu_id_stock": 2, "calories": "0", "picture_file_name": "linsen.jpg"},
        {"id": 4, "name": "Eigenmarke", "qu_id_stock": 2, "calories": None},
        {"id": 5, "name": "Inaktiv", "active": 0},
    ]
    barcodes = [
        {"product_id": 1, "barcode": "4001234567890"},
        {"product_id": 1, "barcode": "4001234567890"},
        {"product_id": 2, "barcode": "4009876543210"},
        {"product_id": 3, "barcode": "40 0555 5555555"},
        {"product_id": 4, "barcode": "grcy:p:4"},
    ]
    candidates, without = plan.select_candidates(products, barcodes, UNITS)
    assert [(c.name, c.barcodes, c.stock_unit, c.needs_calories, c.needs_image) for c in candidates] == [
        ("Linsen", ["4005555555555"], "Stück", True, False),
        ("Reis", ["4001234567890"], "Gramm", True, True),
    ]
    assert without == ["Eigenmarke"]


def test_select_candidates_respects_switches():
    products = [{"id": 1, "name": "Reis", "qu_id_stock": 1, "calories": "3.5"}]
    barcodes = [{"product_id": 1, "barcode": "4001234567890"}]
    assert plan.select_candidates(products, barcodes, UNITS, include_images=False)[0] == []
    assert len(plan.select_candidates(products, barcodes, UNITS)[0]) == 1


def test_plan_update_reports_what_is_missing():
    candidate = plan.Candidate(1, "Linsen", ["4005555555555"], "Stück", True, True)
    update = plan.plan_update(candidate, "4005555555555", {"kcal_100": 330, "package_amount": None, "image_url": ""})
    assert not update.has_changes
    assert update.notes == ["Packungsgröße bei Open Food Facts unbekannt", "kein Bild bei Open Food Facts"]

    update = plan.plan_update(candidate, "4005555555555", {"kcal_100": 330, "package_amount": 500, "image_url": "https://img/l.jpg"})
    assert (update.calories, update.image_url, update.has_changes) == (1650, "https://img/l.jpg", True)


def test_picture_file_name_keeps_extension():
    assert plan.picture_file_name("400123", "https://images.off.org/x/front_de.12.400.jpg") == "off_400123.jpg"
    assert plan.picture_file_name("400123", "https://images.off.org/x/front.png?v=2") == "off_400123.png"
    assert plan.picture_file_name("400123", "https://images.off.org/x/front") == "off_400123.jpg"

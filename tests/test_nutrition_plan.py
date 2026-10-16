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


def test_names_match_catches_wrong_barcode_but_accepts_compounds():
    # echte Fälle aus dem ersten Probelauf
    assert not plan.names_match("Gansterrine mit Pinot Noir", "Terrine de faisan aux raisins")
    assert plan.names_match("Japanese Style Bread Crumbs Panko Flakes", "Japanese Style Bread Crumbs Panko Flakes")
    assert plan.names_match("Milch", "H-Milch fettarm 1,5%")
    assert plan.names_match("Passierte Tomaten", "Tomaten passiert")
    assert plan.names_match("Nudeln - Fusilli Bucati", "Fusilli Bucati")
    # nichts zu vergleichen blockiert nicht
    assert plan.names_match("", "Irgendwas")
    assert plan.names_match("Reis", "")


def test_excluded_groups_default_and_custom():
    assert plan.is_excluded_group("Reinigungsmittel")
    assert plan.is_excluded_group("Haushalt & Drogerie")
    assert not plan.is_excluded_group("Nudeln")
    assert not plan.is_excluded_group("")
    assert plan.is_excluded_group("Gewürze", ["gewürz"])

    products = [
        {"id": 1, "name": "Geschirrreiniger", "product_group_id": 7},
        {"id": 2, "name": "Fusilli", "product_group_id": 8},
        {"id": 3, "name": "Salz", "product_group_id": 9},
        {"id": 4, "name": "Ohne Gruppe"},
    ]
    groups = [{"id": 7, "name": "Reinigungsmittel"}, {"id": 8, "name": "Nudeln"}, {"id": 9, "name": "Gewürze"}]
    kept, excluded = plan.filter_excluded_products(products, groups, ["Gewürze"])
    assert [p["name"] for p in kept] == ["Fusilli", "Ohne Gruppe"]
    assert excluded == ["Geschirrreiniger", "Salz"]


def test_format_package():
    assert plan.format_package(227.0, "g") == "227 g"
    assert plan.format_package(1980.0, "ml") == "1980 ml"
    assert plan.format_package(None, "g") == ""


def test_household_items_recognised_by_name():
    # aus dem zweiten Probelauf: Artikel ohne Reinigungs-Produktgruppe
    for name in ["Putzmittel Küche", "Schimmelentferner", "Spülmittel", "Weichspüler Soft Embrace",
                 "Geschirr Tabs", "Fleckenspray", "Handseife", "Klarspüler", "WC Reiniger",
                 "Waschmaschinen Pfleger", "Backpapier"]:
        assert plan.is_non_food_name(name), name
    # Lebensmittel mit ähnlichen Buchstaben bleiben drin
    for name in ["Tabasco", "Reismehl", "Kaiser-Natron", "Zitronensäure", "Schokolade", "Wasserreis"]:
        assert not plan.is_non_food_name(name), name


def test_filter_excluded_products_also_uses_names():
    products = [
        {"id": 1, "name": "Spülmittel"},
        {"id": 2, "name": "Fusilli", "product_group_id": 8},
        {"id": 3, "name": "Geschirr Tabs"},
    ]
    kept, excluded = plan.filter_excluded_products(products, [{"id": 8, "name": "Nudeln"}])
    assert [p["name"] for p in kept] == ["Fusilli"]
    assert excluded == ["Geschirr Tabs", "Spülmittel"]


def test_coverage_stats_counts_active_products_only():
    products = [
        {"id": 1, "name": "Reis", "calories": "3.5", "picture_file_name": "reis.jpg"},
        {"id": 2, "name": "Linsen", "calories": "0", "picture_file_name": ""},
        {"id": 3, "name": "Inaktiv", "active": 0, "calories": "9"},
        {"id": 4, "name": "Eigenmarke", "calories": None},
    ]
    barcodes = [{"product_id": 1, "barcode": "4001234567890"}, {"product_id": 4, "barcode": "grcy:p:4"}]
    assert plan.coverage_stats(products, barcodes) == {
        "products": 3, "with_barcode": 1, "with_calories": 1, "placeholder_calories": 0, "with_image": 1,
    }


def test_placeholder_calories_are_replaced_but_real_values_are_not():
    products = [
        {"id": 1, "name": "Platzhalter Stück", "qu_id_stock": 2, "calories": "1", "picture_file_name": "x.jpg"},
        {"id": 2, "name": "Echt", "qu_id_stock": 2, "calories": "350", "picture_file_name": "y.jpg"},
        {"id": 3, "name": "Leer", "qu_id_stock": 2, "calories": "0", "picture_file_name": "z.jpg"},
        {"id": 4, "name": "Platzhalter Gramm", "qu_id_stock": 1, "calories": "0.0067", "picture_file_name": "x.jpg"},
        {"id": 5, "name": "Apfelmus", "qu_id_stock": 1, "calories": "0.7", "picture_file_name": "x.jpg"},
        {"id": 6, "name": "Kidneybohnen", "qu_id_stock": 1, "calories": "1", "picture_file_name": "x.jpg"},
        {"id": 7, "name": "Milch", "qu_id_stock": 3, "calories": "1", "picture_file_name": "x.jpg"},
    ]
    barcodes = [{"product_id": i, "barcode": f"400123456789{i}"} for i in range(1, 8)]
    candidates, _ = plan.select_candidates(products, barcodes, UNITS)
    # 0,7 und 1 kcal je Gramm sind echte Werte; Platzhalter je Gramm liegen weit unter 0,1
    assert [(c.name, c.calories_old) for c in candidates] == [
        ("Leer", None), ("Milch", 1.0), ("Platzhalter Gramm", 0.0067), ("Platzhalter Stück", 1.0),
    ]
    # abgeschaltet: nur leere Werte bleiben Kandidaten
    candidates, _ = plan.select_candidates(products, barcodes, UNITS, replace_placeholder=False)
    assert [c.name for c in candidates] == ["Leer"]


def test_coverage_counts_placeholders_separately():
    products = [
        {"id": 1, "name": "A", "qu_id_stock": 2, "calories": "1"},
        {"id": 2, "name": "B", "qu_id_stock": 2, "calories": "250"},
        {"id": 3, "name": "C", "qu_id_stock": 2, "calories": None},
        {"id": 4, "name": "D", "qu_id_stock": 1, "calories": "0.7"},
        {"id": 5, "name": "E", "qu_id_stock": 1, "calories": "0.004"},
    ]
    stats = plan.coverage_stats(products, [], quantity_units=UNITS)
    assert (stats["with_calories"], stats["placeholder_calories"]) == (2, 2)
    stats = plan.coverage_stats(products, [], placeholder_is_empty=False, quantity_units=UNITS)
    assert (stats["with_calories"], stats["placeholder_calories"]) == (4, 0)


def test_zero_kcal_from_open_food_facts_is_not_written():
    candidate = plan.Candidate(1, "Jodsalz", ["4005555555555"], "Gramm", True, False)
    update = plan.plan_update(candidate, "4005555555555", {"kcal_100": 0, "package_amount": 500, "image_url": ""})
    assert not update.has_changes
    assert update.notes == ["0 kcal bei Open Food Facts, nicht geschrieben"]

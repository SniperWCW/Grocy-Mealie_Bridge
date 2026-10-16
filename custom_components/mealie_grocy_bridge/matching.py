"""Ingredient matching between Mealie recipes and Grocy stock.

Pure functions without Home Assistant dependencies, so they can be unit
tested directly and shared by the sensor platform and the meal plan sync.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

EXPIRING_WINDOW_DAYS = 30
EXPIRING_SCORE_BONUS = 15

_WORD_SPLIT = re.compile(r"[\s,()./;:+&\-]+")
_INGREDIENT_WORD_SPLIT = re.compile(r"[\s,()./]+")
_STOCK_WORD_SPLIT = re.compile(r"[\s\-,._()]+")

_NOODLE_KEYWORDS = ("yumyum", "nudeln", "ramen", "reis")
_NOODLE_CONTEXT = ("nudeln", "ramen", "suppe", "yumyum", "reis")
_MEAT_CUTS = ("wings", "schenkel", "filet", "keulen")
_ASIA_KEYWORDS = ("nouilles", "spring", "asia", "happiness")


def ingredient_text(ingredient: dict) -> str:
    """Return the display text of a Mealie ingredient."""
    if not isinstance(ingredient, dict):
        return ""
    return str(
        ingredient.get("display")
        or ingredient.get("note")
        or ingredient.get("originalText")
        or ""
    ).strip()


def recipe_ingredients(recipe: dict) -> list:
    """Return the ingredient list of a Mealie recipe."""
    if not isinstance(recipe, dict):
        return []
    return recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []


def find_basic(text_low: str, basics: list[str]) -> str | None:
    """Return the basic ingredient contained in the text, if any.

    A basic matches a whole word or the end of a German compound word
    ("Olivenöl" -> "öl"), but not the start of one ("Honigmelone" is no
    honey, "Gewürzgurken" are no spice). Multi-word basics are matched as
    a phrase.
    """
    if not text_low:
        return None
    words = [word for word in _WORD_SPLIT.split(text_low) if word]
    for basic in basics:
        basic = basic.strip().lower()
        if not basic:
            continue
        if " " in basic:
            if basic in text_low:
                return basic
            continue
        for word in words:
            if word == basic or word.endswith(basic):
                return basic
    return None


def stock_status(best_before: str | None, today: date) -> str:
    """Classify a Grocy best-before date as normal, expiring or expired."""
    text_value = str(best_before or "").strip()
    if not text_value or text_value.startswith("2999"):
        return "normal"
    try:
        parsed = datetime.strptime(text_value[:10], "%Y-%m-%d").date()
    except ValueError:
        return "normal"
    if parsed < today:
        return "expired"
    if parsed <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
        return "expiring"
    return "normal"


def build_products_map(grocy_stock, today: date) -> dict:
    """Create a normalized lookup map from the Grocy /api/stock response."""
    products_map = {}
    for item in grocy_stock or []:
        if not isinstance(item, dict) or not isinstance(item.get("product"), dict):
            continue
        product_name = item["product"].get("name")
        if not product_name:
            continue
        orig_name = str(product_name).strip()
        name_low = orig_name.lower()
        products_map[name_low] = {
            "orig_name": orig_name,
            "status": stock_status(item.get("best_before_date"), today),
            "regex": re.compile(r"\b" + re.escape(name_low) + r"\b"),
            "words": [
                part.strip()
                for part in _STOCK_WORD_SPLIT.split(name_low)
                if len(part.strip()) > 2
            ],
        }
    return products_map


def _plural_match(word: str, stock_word: str) -> bool:
    return (
        word == stock_word
        or word + "n" == stock_word
        or word + "s" == stock_word
        or word + "en" == stock_word
        or stock_word + "n" == word
        or stock_word + "s" == word
    )


def find_product(ing_text_low: str, products_map: dict) -> dict | None:
    """Find the Grocy product that matches an ingredient text."""
    ing_words = [
        word
        for word in _INGREDIENT_WORD_SPLIT.split(ing_text_low)
        if len(word) > 2 and not word.isdigit()
    ]

    # Pass 1: strict match of the full product name on word boundaries.
    for stock_low, info in products_map.items():
        if any(kw in stock_low for kw in _NOODLE_KEYWORDS):
            if any(cut in ing_text_low for cut in _MEAT_CUTS):
                continue
            if any(kw in stock_low for kw in _ASIA_KEYWORDS) and not any(
                kw in ing_text_low for kw in _ASIA_KEYWORDS
            ):
                continue
        if info["regex"].search(ing_text_low):
            return info

    # Pass 2: word-wise match with simple plural tolerance.
    for stock_low, info in products_map.items():
        stock_words = info["words"]
        if not stock_words:
            continue

        if any(kw in stock_low for kw in _NOODLE_KEYWORDS):
            if any(cut in ing_text_low for cut in _MEAT_CUTS):
                continue
            if not any(kw in ing_text_low for kw in _NOODLE_CONTEXT):
                continue
            if any(kw in stock_low for kw in _ASIA_KEYWORDS) and not any(
                kw in ing_text_low for kw in _ASIA_KEYWORDS
            ):
                continue
            if "wan-tan" in stock_low and "wan-tan" not in ing_text_low:
                continue

        if "chicken" in ing_words and "chicken" in stock_words:
            if "wings" in ing_words and "wings" not in stock_words:
                continue
            if "nuggets" in ing_words and "nuggets" not in stock_words:
                continue

        if any(_plural_match(word, stock_word) for word in ing_words for stock_word in stock_words):
            return info

    return None


def clean_basic_ingredient(text_low: str, fallback: str) -> str:
    """Strip amounts and units from a basic ingredient for display."""
    cleaned_text = re.sub(r"\s+", " ", str(text_low or "").lower().replace("-", " ").strip())
    quantity_pattern = r"^\s*(?:\d+\s*/\s*\d+|\d+[.,]?\d*|[¼½¾⅓⅔⅛⅜⅝⅞])\s*"
    unit_pattern = (
        r"^\s*(?:tl|el|g|kg|mg|ml|cl|dl|l|liter|bund|stück|stueck|stck|"
        r"zehe|zehen|prise|prisen|becher|dose|päckchen|paeckchen)\b\s*"
    )

    changed = True
    while cleaned_text and changed:
        previous = cleaned_text
        cleaned_text = re.sub(quantity_pattern, "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(unit_pattern, "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = cleaned_text.strip(" ,.")
        changed = cleaned_text != previous

    if not cleaned_text or len(cleaned_text) <= 2:
        cleaned_text = fallback
    return cleaned_text.strip().capitalize()


def analyze_recipe(recipe: dict, products_map: dict, basics: list[str]) -> dict:
    """Match all ingredients of one recipe against the Grocy stock."""
    matching = []
    missing = []
    basic_details = []
    relevant_total = 0
    has_expiring = False

    for ingredient in recipe_ingredients(recipe):
        text = ingredient_text(ingredient)
        text_low = text.lower()
        if not text_low:
            continue

        basic = find_basic(text_low, basics)
        if basic:
            basic_details.append(clean_basic_ingredient(text_low, basic))
            continue

        relevant_total += 1
        product = find_product(text_low, products_map)
        if product:
            matching.append({"name": product["orig_name"], "status": product["status"]})
            if product["status"] in ("expired", "expiring"):
                has_expiring = True
        else:
            missing.append(text[0].upper() + text[1:])

    score = 0
    if relevant_total and matching:
        score = round(len(matching) / relevant_total * 100)
        if has_expiring:
            score = min(100, score + EXPIRING_SCORE_BONUS)

    return {
        "matchingIngredients": matching,
        "missingIngredients": missing,
        "basicIngredients": sorted(set(basic_details)),
        "matchCount": len(matching),
        "relevantTotal": relevant_total,
        "matchScore": score,
        "hasExpiring": has_expiring,
    }


def normalize_list_item(text: str) -> str:
    """Normalize to-do items for duplicate comparison."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())

"""Plan which Grocy products get calories and pictures from Open Food Facts.

Pure functions without Home Assistant, so they can be unit tested. The
async runner in ``openfoodfacts.py`` fetches the data and applies the plan.

Grocy stores calories per *stock quantity unit* (field hint "Per stock
quantity unit"), Open Food Facts per 100 g or 100 ml. For weight and volume
units the value is scaled; for pieces, packs, cans and the like the package
size from Open Food Facts is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KJ_PER_KCAL = 4.184
MAX_KCAL_PER_100 = 900  # pure fat is about 900 kcal/100 g, anything above is a data error

# Normalized unit name -> factor relative to 100 g / 100 ml
_SCALED_UNITS = {
    "g": 0.01, "gr": 0.01, "gramm": 0.01, "gram": 0.01, "grams": 0.01,
    "kg": 10, "kilo": 10, "kilogramm": 10, "kilogram": 10,
    "ml": 0.01, "milliliter": 0.01, "millilitre": 0.01,
    "cl": 0.1, "dl": 1,
    "l": 10, "liter": 10, "litre": 10, "liters": 10,
}
# Units that mean "one package" – calories come from the package size
_PACKAGE_UNITS = {
    "stuck", "stueck", "stk", "st", "piece", "pieces", "pc", "pcs",
    "packung", "packungen", "pack", "packs", "pkg", "paket", "pakete",
    "dose", "dosen", "can", "cans", "glas", "glaser", "jar", "jars",
    "flasche", "flaschen", "bottle", "bottles", "becher", "tute", "tuten", "beutel",
    "tube", "tuben", "karton", "kartons", "box", "schachtel", "netz", "bund",
    "portion", "portionen", "riegel", "tafel", "tafeln",
}


def normalize_unit(value) -> str:
    """Lower-case a unit name, fold umlauts, keep only letters."""
    text = str(value or "").strip().lower()
    for src, dst in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        text = text.replace(src, dst)
    return re.sub(r"[^a-z]", "", text)


# Product groups that never hold food. Matched as substrings of the normalized group name.
DEFAULT_EXCLUDED_GROUPS = (
    "reinig", "haushalt", "drogerie", "hygiene", "kosmetik", "tierbedarf", "putz", "wasch",
)
_NAME_STOPWORDS = {
    "mit", "und", "von", "the", "and", "with", "aux", "des", "les", "pro", "bio", "ohne",
    "in", "im", "aus", "fur", "fuer", "de", "du", "la", "le", "au", "en", "da", "di",
}


def _to_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ".").strip())
    except ValueError:
        return None
    return number if number == number else None  # drop NaN


def parse_package_quantity(product: dict) -> tuple[float | None, str]:
    """Return the package size and its unit ("g" or "ml") from an OFF product."""
    amount = _to_float(product.get("product_quantity"))
    unit = normalize_unit(product.get("product_quantity_unit")) or "g"
    if amount is None:
        # Fallback: free text like "400 g", "0,7 l", "6 x 330 ml"
        match = re.search(
            r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\b",
            str(product.get("quantity") or "").lower(),
        )
        if not match:
            return None, ""
        count = int(match.group(1) or 1)
        amount = count * float(match.group(2).replace(",", "."))
        unit = match.group(3)
    factors = {"g": (1, "g"), "kg": (1000, "g"), "mg": (0.001, "g"),
               "ml": (1, "ml"), "cl": (10, "ml"), "dl": (100, "ml"), "l": (1000, "ml")}
    if unit not in factors or amount <= 0:
        return None, ""
    factor, base = factors[unit]
    return amount * factor, base


def parse_off_product(payload: dict) -> dict | None:
    """Extract the fields the bridge uses from an Open Food Facts API response."""
    if not isinstance(payload, dict) or payload.get("status") != 1:
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    nutriments = product.get("nutriments") or {}
    kcal = _to_float(nutriments.get("energy-kcal_100g"))
    if kcal is None:
        kj = _to_float(nutriments.get("energy-kj_100g"))
        if kj is None and normalize_unit(nutriments.get("energy_unit")) in ("", "kj"):
            kj = _to_float(nutriments.get("energy_100g"))
        if kj is not None:
            kcal = kj / KJ_PER_KCAL
    if kcal is not None and not 0 <= kcal <= MAX_KCAL_PER_100:
        kcal = None

    package_amount, package_unit = parse_package_quantity(product)
    return {
        "name": str(product.get("product_name_de") or product.get("product_name") or "").strip(),
        "kcal_100": kcal,
        "package_amount": package_amount,
        "package_unit": package_unit,
        "image_url": str(product.get("image_front_url") or product.get("image_url") or "").strip(),
    }


def kcal_per_stock_unit(kcal_100: float | None, unit_name, package_amount=None) -> tuple[float | None, str]:
    """Convert kcal per 100 g/ml into kcal per Grocy stock unit.

    Returns the value (rounded to one decimal) or None plus a short German reason.
    """
    if kcal_100 is None:
        return None, "keine Kalorien bei Open Food Facts"
    unit = normalize_unit(unit_name)
    if unit in _SCALED_UNITS:
        return round(kcal_100 * _SCALED_UNITS[unit], 1), ""
    if unit in _PACKAGE_UNITS or not unit:
        if not package_amount:
            return None, "Packungsgröße bei Open Food Facts unbekannt"
        return round(kcal_100 * package_amount / 100, 1), ""
    return None, f"Einheit „{unit_name}“ nicht umrechenbar"


@dataclass
class Candidate:
    """A Grocy product that is missing calories and/or a picture."""

    product_id: int
    name: str
    barcodes: list[str]
    stock_unit: str
    needs_calories: bool
    needs_image: bool


@dataclass
class ProductUpdate:
    """What to write back to Grocy for one product."""

    product_id: int
    name: str
    barcode: str
    calories: float | None = None
    image_url: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return self.calories is not None or bool(self.image_url)


def _name_tokens(text) -> list[str]:
    folded = str(text or "").lower()
    for src, dst in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("é", "e"), ("è", "e"), ("ê", "e")):
        folded = folded.replace(src, dst)
    return [
        token for token in re.findall(r"[a-z0-9]+", folded)
        if len(token) >= 3 and token not in _NAME_STOPWORDS and not token.isdigit()
    ]


def names_match(grocy_name, off_name) -> bool:
    """Rough check that an Open Food Facts product is the one meant in Grocy.

    At least half of the meaningful words of the Grocy name must appear in the
    Open Food Facts name (as a whole word or, from 5 letters on, as part of a
    compound: "Gansterrine" contains "terrine"). Names are often in another
    language, so a failed check only means "please look at this", not "wrong".
    """
    grocy_tokens = _name_tokens(grocy_name)
    off_tokens = _name_tokens(off_name)
    if not grocy_tokens or not off_tokens:
        return True  # nothing to compare, do not block
    matched = 0
    for token in grocy_tokens:
        for other in off_tokens:
            if token == other or (len(other) >= 5 and other in token) or (len(token) >= 5 and token in other):
                matched += 1
                break
    return matched / len(grocy_tokens) >= 0.5


def is_excluded_group(group_name, extra_groups=()) -> bool:
    """True for product groups that should be skipped (household items etc.)."""
    name = normalize_unit(group_name)
    if not name:
        return False
    patterns = list(DEFAULT_EXCLUDED_GROUPS) + [normalize_unit(group) for group in extra_groups or []]
    return any(pattern and pattern in name for pattern in patterns)


def filter_excluded_products(products, product_groups, extra_groups=()):
    """Split products into (kept, names of excluded ones) by Grocy product group."""
    group_names = {
        str(group.get("id")): str(group.get("name") or "")
        for group in product_groups or []
        if isinstance(group, dict)
    }
    kept, excluded = [], []
    for product in products or []:
        group = group_names.get(str(product.get("product_group_id")), "") if isinstance(product, dict) else ""
        if group and is_excluded_group(group, extra_groups):
            excluded.append(str(product.get("name") or "").strip())
        else:
            kept.append(product)
    return kept, sorted(excluded, key=str.lower)


def format_package(amount, unit) -> str:
    """Human readable package size for the report, e.g. "227 g"."""
    if not amount or not unit:
        return ""
    return f"{amount:g} {unit}"


def _is_empty_calories(value) -> bool:
    number = _to_float(value)
    return number is None or number <= 0


def select_candidates(products, barcodes, quantity_units, include_calories=True, include_images=True):
    """Return products with a barcode that lack calories or a picture.

    Products without a barcode are returned separately (by name) so the
    report can list them.
    """
    unit_names = {}
    for unit in quantity_units or []:
        if isinstance(unit, dict) and unit.get("id") is not None:
            unit_names[str(unit["id"])] = str(unit.get("name") or "")

    barcode_map: dict[str, list[str]] = {}
    for entry in barcodes or []:
        if not isinstance(entry, dict):
            continue
        code = re.sub(r"\s+", "", str(entry.get("barcode") or ""))
        if not code.isdigit() or len(code) < 8:
            continue  # Grocy-internal codes ("grcy:p:12") are not EAN/UPC
        codes = barcode_map.setdefault(str(entry.get("product_id")), [])
        if code not in codes:
            codes.append(code)

    candidates: list[Candidate] = []
    without_barcode: list[str] = []
    for product in products or []:
        if not isinstance(product, dict) or product.get("id") is None:
            continue
        if str(product.get("active", 1)) in ("0", "False", "false"):
            continue
        needs_calories = include_calories and _is_empty_calories(product.get("calories"))
        needs_image = include_images and not str(product.get("picture_file_name") or "").strip()
        if not (needs_calories or needs_image):
            continue
        name = str(product.get("name") or "").strip()
        codes = barcode_map.get(str(product["id"]), [])
        if not codes:
            without_barcode.append(name)
            continue
        candidates.append(
            Candidate(
                product_id=int(product["id"]),
                name=name,
                barcodes=codes,
                stock_unit=unit_names.get(str(product.get("qu_id_stock")), ""),
                needs_calories=needs_calories,
                needs_image=needs_image,
            )
        )
    candidates.sort(key=lambda candidate: candidate.name.lower())
    without_barcode.sort(key=str.lower)
    return candidates, without_barcode


def plan_update(candidate: Candidate, barcode: str, off_product: dict) -> ProductUpdate:
    """Decide what to write for one product, given its Open Food Facts data."""
    update = ProductUpdate(product_id=candidate.product_id, name=candidate.name, barcode=barcode)
    if candidate.needs_calories:
        calories, reason = kcal_per_stock_unit(
            off_product.get("kcal_100"), candidate.stock_unit, off_product.get("package_amount")
        )
        if calories is not None:
            update.calories = calories
        else:
            update.notes.append(reason)
    if candidate.needs_image:
        if off_product.get("image_url"):
            update.image_url = off_product["image_url"]
        else:
            update.notes.append("kein Bild bei Open Food Facts")
    return update


def picture_file_name(barcode: str, image_url: str) -> str:
    """File name for the uploaded picture, e.g. ``off_4001234567890.jpg``."""
    match = re.search(r"\.(jpe?g|png|webp)(?:\?|$)", image_url.lower())
    extension = match.group(1).replace("jpeg", "jpg") if match else "jpg"
    return f"off_{barcode}.{extension}"

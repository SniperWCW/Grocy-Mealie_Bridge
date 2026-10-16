"""Pure planning logic for the Grocy shopping list transfer (no HA imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


def normalize_item_name(value) -> str:
    """Normalize names for duplicate detection (case, accents, punctuation)."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def format_amount(amount) -> str:
    """Format Grocy amounts without trailing zeros."""
    try:
        number = float(amount)
    except (TypeError, ValueError):
        return "1"
    if number <= 0:
        return "1"
    return f"{number:.2f}".rstrip("0").rstrip(".")


@dataclass
class PlannedTransfer:
    """One Grocy shopping list entry and what to do with it."""

    grocy_id: int
    name: str
    description: str
    already_on_list: bool


@dataclass
class TransferPlan:
    """Result of comparing the Grocy list with the to-do list."""

    transfers: list[PlannedTransfer] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def plan_transfer(shopping_items, products, quantity_units, existing_names) -> TransferPlan:
    """Decide which Grocy entries to add and which are already on the list.

    Pure function so it can be unit tested without Home Assistant.
    """
    product_map = {str(p.get("id")): p for p in products or [] if isinstance(p, dict)}
    unit_map = {
        str(u.get("id")): str(u.get("name") or "").strip()
        for u in quantity_units or []
        if isinstance(u, dict)
    }
    seen = {normalize_item_name(name) for name in existing_names if name}
    plan = TransferPlan()

    for item in shopping_items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("done") or "0") not in ("0", "", "False", "false"):
            continue

        product = product_map.get(str(item.get("product_id"))) if item.get("product_id") else None
        name = str((product or {}).get("name") or item.get("note") or "").strip()
        if not name:
            plan.unresolved.append(f"Grocy-Eintrag {item.get('id')}: kein Produktname")
            continue

        unit_id = item.get("qu_id") or (product or {}).get("qu_id_purchase") or (product or {}).get("qu_id_stock")
        unit = unit_map.get(str(unit_id), "") if unit_id else ""
        amount = format_amount(item.get("amount"))
        description = f"{amount} {unit} für Grocy" if unit else f"{amount}x für Grocy"
        if product and item.get("note"):
            description = f"{description} ({str(item['note']).strip()})"

        normalized = normalize_item_name(name)
        plan.transfers.append(
            PlannedTransfer(
                grocy_id=int(item["id"]),
                name=name,
                description=description,
                already_on_list=normalized in seen,
            )
        )
        seen.add(normalized)

    return plan

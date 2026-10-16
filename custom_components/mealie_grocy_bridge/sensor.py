"""Sensor platform for Mealie Grocy Bridge."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from urllib.parse import quote

import aiohttp

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    CONF_GROCY_TOKEN,
    CONF_GROCY_URL,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    CONF_MEALPLAN_WINDOW_DAYS,
    CONF_MEALPLAN_WINDOW_MODE,
    DOMAIN,
    MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK,
    MEALPLAN_WINDOW_CURRENT_WEEK,
    MEALPLAN_WINDOW_NEXT_WEEK,
    MEALPLAN_WINDOW_TODAY_PLUS_DAYS,
    REQUEST_TIMEOUT,
    WEEKDAY_NAMES_DE,
    normalize_base_url,
    parse_mealplan_date,
)
from .matching import analyze_recipe, build_products_map, stock_status
from .nutrition_plan import real_calories

_LOGGER = logging.getLogger(__name__)
RECIPE_CACHE_MAX_AGE = timedelta(hours=6)

DEFAULT_BASICS = [
    "salz", "pfeffer", "wasser", "öl", "zucker", "mehl", "gewürz", "prise", "etwas",
    "kümmel", "basilikum", "cayennepfeffer", "chilli", "curry", "honig", "koriander",
    "kurkuma", "majoran", "meersalz", "muskat", "oregano", "paprikapulver",
    "petersilie", "schnittlauch", "thymian"
]

UNKNOWN_LOCATION = "Nicht zugeordnet"

UNIT_ALIASES = {
    "g": "g",
    "gramm": "g",
    "gram": "g",
    "gr": "g",
    "kg": "kg",
    "kilogramm": "kg",
    "kilogram": "kg",
    "mg": "mg",
    "ml": "ml",
    "milliliter": "ml",
    "millilitre": "ml",
    "l": "l",
    "lt": "l",
    "liter": "l",
    "litre": "l",
    "cl": "cl",
    "dl": "dl",
    "stk": "piece",
    "stck": "piece",
    "stueck": "piece",
    "stuck": "piece",
    "stuecke": "piece",
    "portion": "piece",
    "portionen": "piece",
    "pcs": "piece",
    "pc": "piece",
    "piece": "piece",
    "pieces": "piece",
    "egg": "piece",
    "eggs": "piece",
}


def _safe_float(value, default=0.0):
    """Convert mixed API values into floats."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)

    text_value = str(value).strip().replace(",", ".")
    try:
        return float(text_value)
    except ValueError:
        return default


def _first_non_empty(*values):
    """Return the first non-empty value from a list."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_unit(unit_value):
    """Normalize Grocy quantity units into a compact internal form."""
    raw_unit = str(unit_value or "").strip().lower()
    if not raw_unit:
        return ""
    return UNIT_ALIASES.get(raw_unit, raw_unit)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    coordinator = MealieGrocyBridgeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    integration = await async_get_integration(hass, DOMAIN)
    integration_version = str(integration.version or "")
    async_add_entities(
        [
            MealieGrocySensor(coordinator, entry.entry_id, integration_version),
            MealieGrocyInventorySensor(coordinator, entry.entry_id, integration_version),
            MealieGrocyEmergencySupplySensor(
                coordinator,
                entry.entry_id,
                integration_version,
            ),
        ]
    )


class MealieGrocyBridgeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mealie and Grocy data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry_id = entry.entry_id
        self.session = async_get_clientsession(hass)
        self.mealplan = []
        self.mealplan_range = {"start": None, "end": None, "mode": None, "label": None}
        self.stock_items = []
        self.inventory_items = []
        self.inventory_locations = []
        self._planned_identifiers = set()
        self._recipe_cache = {}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )

    @staticmethod
    def _get_current_week_bounds(today):
        """Return the current Saturday-based week bounds."""
        days_since_saturday = (today.weekday() - 5) % 7
        week_start = today - timedelta(days=days_since_saturday)
        week_end = week_start + timedelta(days=7)
        return week_start, week_end

    @classmethod
    def _resolve_mealplan_window(cls, today, config_entry_data):
        """Resolve the configured meal plan window and display label."""
        mode = config_entry_data.get(CONF_MEALPLAN_WINDOW_MODE, MEALPLAN_WINDOW_CURRENT_WEEK)
        current_week_start, current_week_end = cls._get_current_week_bounds(today)

        if mode == MEALPLAN_WINDOW_NEXT_WEEK:
            start = current_week_end
            end = start + timedelta(days=7)
            label = "Nächste Woche"
        elif mode == MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK:
            start = current_week_start
            end = current_week_end + timedelta(days=7)
            label = "Aktuelle und nächste Woche"
        elif mode == MEALPLAN_WINDOW_TODAY_PLUS_DAYS:
            try:
                days = int(config_entry_data.get(CONF_MEALPLAN_WINDOW_DAYS, 7))
            except (TypeError, ValueError):
                days = 7
            days = max(0, min(days, 14))
            start = today
            end = today + timedelta(days=days)
            label = f"Heute + {days} Tage"
        else:
            start = current_week_start
            end = current_week_end
            label = "Aktuelle Woche"

        return start, end, mode, label

    @staticmethod
    def _extract_mealplan_items(raw_data):
        """Normalize mealplan API payloads to a list of items."""
        if isinstance(raw_data, list):
            return raw_data
        if isinstance(raw_data, dict):
            return raw_data.get("items", raw_data.get("data", []))
        return []

    @staticmethod
    def _extract_recipe_name(plan):
        """Extract a human-friendly recipe name from a mealplan entry."""
        recipe_obj = plan.get("recipe")
        if isinstance(recipe_obj, dict):
            for key in ("name", "title"):
                value = recipe_obj.get(key)
                if value:
                    return str(value).strip()
        for key in ("title", "text", "note"):
            value = plan.get(key)
            if value:
                return str(value).strip()
        return "Unbekannt"

    @staticmethod
    def _normalize_duration(value):
        """Normalize duration values from Mealie into displayable text."""
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return f"{int(value)} min"
        text_value = str(value).strip()
        if not text_value:
            return None
        return text_value

    @staticmethod
    def _build_recipe_image_url(mealie_url, recipe_id, image_version=None, image_type="min-original.webp"):
        """Build an official Mealie recipe image URL."""
        recipe_id = str(recipe_id or "").strip()
        if not recipe_id:
            return None

        version = str(image_version or "").strip()
        return (
            f"{mealie_url}/api/media/recipes/{quote(recipe_id, safe='')}/images/{image_type}"
            f"?rnd=1&version={quote(version, safe='')}"
        )

    @staticmethod
    def _extract_recipe_image(plan, mealie_url):
        """Extract a recipe image URL from a mealplan entry when available."""
        recipe_obj = plan.get("recipe")
        if not isinstance(recipe_obj, dict):
            return None

        for key in ("imageUrl", "recipeImage", "thumbnail"):
            value = recipe_obj.get(key)
            if isinstance(value, str) and value.strip():
                if value.startswith(("http://", "https://")):
                    return value.strip()
                return f"{mealie_url}/{value.lstrip('/')}"

        recipe_asset = recipe_obj.get("recipeAsset")
        if isinstance(recipe_asset, dict):
            for key in ("image", "url", "path"):
                value = recipe_asset.get(key)
                if isinstance(value, str) and value.strip():
                    if value.startswith(("http://", "https://")):
                        return value.strip()
                    return f"{mealie_url}/{value.lstrip('/')}"

        recipe_id = recipe_obj.get("id") or plan.get("recipeId")
        image_version = recipe_obj.get("image")
        return MealieGrocyBridgeCoordinator._build_recipe_image_url(mealie_url, recipe_id, image_version)

    @classmethod
    def _extract_mealplan_recipe_meta(cls, plan, mealie_url):
        """Extract image and timing metadata from a mealplan recipe."""
        recipe_obj = plan.get("recipe")
        recipe_meta = {
            "imageUrl": cls._extract_recipe_image(plan, mealie_url),
            "imageFallbackUrl": None,
            "prepTime": None,
            "cookTime": None,
            "totalTime": None,
        }

        if not isinstance(recipe_obj, dict):
            return recipe_meta

        recipe_id = recipe_obj.get("id") or plan.get("recipeId")
        image_version = recipe_obj.get("image")
        if not recipe_meta["imageUrl"]:
            recipe_meta["imageUrl"] = cls._build_recipe_image_url(
                mealie_url, recipe_id, image_version, "min-original.webp"
            )
        recipe_meta["imageFallbackUrl"] = cls._build_recipe_image_url(
            mealie_url, recipe_id, image_version, "original.webp"
        )

        recipe_meta["prepTime"] = cls._normalize_duration(
            recipe_obj.get("prepTime") or recipe_obj.get("prepTimeMinutes")
        )
        recipe_meta["cookTime"] = cls._normalize_duration(
            recipe_obj.get("cookTime")
            or recipe_obj.get("performTime")
            or recipe_obj.get("performTimeMinutes")
        )
        recipe_meta["totalTime"] = cls._normalize_duration(
            recipe_obj.get("totalTime") or recipe_obj.get("totalTimeMinutes")
        )

        return recipe_meta

    @staticmethod
    def _extract_stock_unit(item):
        """Extract the most useful stock unit label from Grocy stock payloads."""
        product = item.get("product") if isinstance(item, dict) else {}
        quantity_unit_stock = item.get("quantity_unit_stock") if isinstance(item, dict) else None
        if isinstance(quantity_unit_stock, dict):
            quantity_unit_stock = quantity_unit_stock.get("name")

        explicit_stock_unit = _normalize_unit(
            _first_non_empty(
                item.get("quantity_unit_stock_name"),
                quantity_unit_stock,
            )
        )
        if explicit_stock_unit:
            return explicit_stock_unit, "quantity_unit_stock_name"

        product_quantity_unit = product.get("quantity_unit_stock") if isinstance(product, dict) else None
        if isinstance(product_quantity_unit, dict):
            product_quantity_unit = product_quantity_unit.get("name")

        product_stock_unit = _normalize_unit(
            _first_non_empty(
                product.get("quantity_unit_stock_name") if isinstance(product, dict) else None,
                product_quantity_unit,
            )
        )
        if product_stock_unit:
            return product_stock_unit, "product.quantity_unit_stock"

        return "", ""

    @staticmethod
    def _build_quantity_unit_map(quantity_units):
        """Build an id-to-name map from Grocy quantity units."""
        unit_map = {}
        for unit in quantity_units or []:
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("id")
            unit_name = unit.get("name")
            if unit_id is None or not unit_name:
                continue
            try:
                unit_map[int(unit_id)] = _normalize_unit(unit_name)
            except (TypeError, ValueError):
                continue
        return unit_map

    @staticmethod
    def _build_id_name_map(objects):
        """Build a numeric id-to-name map from a Grocy object response."""
        object_map = {}
        for item in objects or []:
            if not isinstance(item, dict):
                continue
            object_id = item.get("id")
            name = str(item.get("name") or "").strip()
            if object_id is None or not name:
                continue
            try:
                object_map[int(object_id)] = name
            except (TypeError, ValueError):
                continue
        return object_map

    @staticmethod
    def _extract_product_id(item):
        """Extract a product id from the different Grocy stock payload shapes."""
        if not isinstance(item, dict):
            return None
        product = item.get("product")
        candidates = [
            item.get("product_id"),
            product.get("id") if isinstance(product, dict) else None,
        ]
        for candidate in candidates:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_location_id(item):
        """Extract the best available location id from a Grocy payload."""
        if not isinstance(item, dict):
            return None

        product = item.get("product")
        location = item.get("location")
        product_location = product.get("location") if isinstance(product, dict) else None
        candidates = [
            item.get("location_id"),
            item.get("current_location_id"),
            location.get("id") if isinstance(location, dict) else None,
            product.get("location_id") if isinstance(product, dict) else None,
            product_location.get("id") if isinstance(product_location, dict) else None,
        ]
        for candidate in candidates:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_api_items(raw_data):
        """Normalize common Grocy list response shapes."""
        if isinstance(raw_data, list):
            return raw_data
        if isinstance(raw_data, dict):
            return raw_data.get("items", raw_data.get("data", []))
        return []

    @staticmethod
    def _resolve_stock_unit_by_id(item, quantity_unit_map):
        """Resolve stock unit name from Grocy quantity unit ids."""
        if not quantity_unit_map or not isinstance(item, dict):
            return ""

        product = item.get("product") if isinstance(item, dict) else {}
        candidate_ids = [
            item.get("qu_id_stock"),
            item.get("quantity_unit_stock_id"),
            product.get("qu_id_stock") if isinstance(product, dict) else None,
        ]

        for candidate_id in candidate_ids:
            try:
                normalized_id = int(candidate_id)
            except (TypeError, ValueError):
                continue
            resolved_unit = quantity_unit_map.get(normalized_id)
            if resolved_unit:
                return resolved_unit

        return ""

    @staticmethod
    def _extract_stock_amount(item):
        """Extract the stock amount from the most stock-specific Grocy fields."""
        if not isinstance(item, dict):
            return 0.0, ""

        for field_name in ("stock_amount", "amount_aggregated", "amount", "quantity"):
            amount = _safe_float(item.get(field_name))
            if amount > 0:
                return amount, field_name

        return 0.0, ""

    @staticmethod
    def _extract_stock_snapshot(
        item,
        quantity_unit_map=None,
        location_map=None,
        product_group_map=None,
    ):
        """Build a normalized stock snapshot for the emergency supply card."""
        if not isinstance(item, dict):
            return None

        product = item.get("product")
        if not isinstance(product, dict):
            return None

        product_name = str(product.get("name") or "").strip()
        if not product_name:
            return None

        amount, amount_source = MealieGrocyBridgeCoordinator._extract_stock_amount(item)
        if amount <= 0:
            return None

        product_group = product.get("product_group")
        if isinstance(product_group, dict):
            product_group = product_group.get("name")
        if not product_group:
            try:
                product_group_id = int(product.get("product_group_id"))
            except (TypeError, ValueError):
                product_group_id = None
            product_group = (product_group_map or {}).get(product_group_id)

        unit, unit_source = MealieGrocyBridgeCoordinator._extract_stock_unit(item)
        if not unit:
            unit = MealieGrocyBridgeCoordinator._resolve_stock_unit_by_id(item, quantity_unit_map)
            if unit:
                unit_source = "quantity_unit_map"

        location_id = MealieGrocyBridgeCoordinator._extract_location_id(item)
        embedded_location = _first_non_empty(
            item.get("location_name"),
            item.get("location", {}).get("name") if isinstance(item.get("location"), dict) else None,
            product.get("location", {}).get("name")
            if isinstance(product.get("location"), dict)
            else None,
        )
        location_name = str(
            embedded_location
            or (location_map or {}).get(location_id)
            or UNKNOWN_LOCATION
        ).strip()

        return {
            "product_id": MealieGrocyBridgeCoordinator._extract_product_id(item),
            "name": product_name,
            "amount": amount,
            "amount_source": amount_source,
            "unit": unit,
            "unit_source": unit_source,
            "qu_id_stock": item.get("qu_id_stock"),
            "quantity_unit_stock_id": item.get("quantity_unit_stock_id"),
            "best_before_date": item.get("best_before_date"),
            "product_group": str(product_group or "").strip(),
            "calories": real_calories(product.get("calories"), unit),
            "location_id": location_id,
            "location": location_name,
            "location_source": "product_default" if location_id is not None else "unknown",
        }

    @staticmethod
    def _build_inventory_items(stock_items, product_locations, location_map, today=None):
        """Expand aggregated Grocy stock into one frontend item per current location."""
        inventory_items = []
        expiration_limit = today + timedelta(days=30) if today else None

        for stock_item in stock_items:
            product_id = stock_item.get("product_id")
            location_rows = product_locations.get(product_id, [])
            resolved_rows = {}

            for row in location_rows:
                if not isinstance(row, dict):
                    continue
                amount = _safe_float(row.get("amount"))
                if amount <= 0:
                    continue
                location_id = MealieGrocyBridgeCoordinator._extract_location_id(row)
                location_name = str(
                    _first_non_empty(
                        row.get("location_name"),
                        row.get("location", {}).get("name")
                        if isinstance(row.get("location"), dict)
                        else None,
                        location_map.get(location_id),
                    )
                    or UNKNOWN_LOCATION
                ).strip()
                row_key = (location_id, location_name)
                resolved = resolved_rows.setdefault(row_key, {"amount": 0.0, "dates": []})
                resolved["amount"] += amount
                best_before_date = str(row.get("best_before_date") or "").strip()
                if best_before_date and not best_before_date.startswith("2999"):
                    resolved["dates"].append(best_before_date)

            if resolved_rows:
                for (location_id, location_name), resolved in resolved_rows.items():
                    best_before_date = min(resolved["dates"], default=stock_item.get("best_before_date"))
                    status = stock_item.get("status", "normal")
                    if today and best_before_date:
                        try:
                            parsed_date = datetime.strptime(str(best_before_date), "%Y-%m-%d").date()
                            status = (
                                "expired"
                                if parsed_date < today
                                else "expiring"
                                if parsed_date <= expiration_limit
                                else "normal"
                            )
                        except ValueError:
                            pass
                    inventory_items.append(
                        {
                            **stock_item,
                            "amount": resolved["amount"],
                            "amount_source": "stock_location.amount",
                            "best_before_date": best_before_date,
                            "status": status,
                            "location_id": location_id,
                            "location": location_name,
                            "location_source": "current_stock",
                        }
                    )
                continue

            inventory_items.append(stock_item.copy())

        inventory_items.sort(
            key=lambda entry: (
                str(entry.get("location") or UNKNOWN_LOCATION).casefold(),
                str(entry.get("name") or "").casefold(),
            )
        )
        return inventory_items

    @staticmethod
    def _build_location_summaries(inventory_items):
        """Create compact per-location counters without duplicating every stock item."""
        locations = {}
        for item in inventory_items:
            location_name = str(item.get("location") or UNKNOWN_LOCATION).strip()
            summary = locations.setdefault(
                location_name,
                {
                    "name": location_name,
                    "item_count": 0,
                    "normal_count": 0,
                    "expiring_count": 0,
                    "expired_count": 0,
                },
            )
            summary["item_count"] += 1
            status = str(item.get("status") or "normal")
            status_key = f"{status}_count"
            if status_key in summary:
                summary[status_key] += 1

        return sorted(locations.values(), key=lambda location: location["name"].casefold())

    async def _fetch_stock_entries(self, grocy_url, headers):
        """Fetch all individual Grocy stock entries in one request.

        Returns None when the request fails, so the caller can fall back to
        the slower per-location endpoint.
        """
        try:
            async with self.session.get(
                f"{grocy_url}/api/objects/stock",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 200:
                    return self._extract_api_items(await response.json())
                _LOGGER.debug("Grocy-Bestandseintraege nicht abrufbar (%s)", response.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Grocy-Bestandseintraege nicht abrufbar: %s", err)
        return None

    async def _fetch_location_entries(self, semaphore, location_id, grocy_url, headers):
        """Fetch all current stock entries for one location (fallback)."""
        async with semaphore:
            try:
                async with self.session.get(
                    f"{grocy_url}/api/stock/locations/{location_id}/entries",
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    if response.status == 200:
                        return location_id, self._extract_api_items(await response.json())
                    _LOGGER.debug(
                        "Grocy-Bestand fuer Lagerort %s konnte nicht geladen werden (%s)",
                        location_id,
                        response.status,
                    )
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug(
                    "Grocy-Bestand fuer Lagerort %s konnte nicht geladen werden: %s",
                    location_id,
                    err,
                )
            return location_id, []

    async def _fetch_recipe_details(self, semaphore, slug, mealie_url, headers):
        """Fetch full details for a single recipe with a concurrency limit."""
        async with semaphore:
            try:
                async with self.session.get(
                    f"{mealie_url}/api/recipes/{slug}",
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as res:
                    if res.status == 200:
                        return await res.json()
                    _LOGGER.debug("Rezept %s nicht abrufbar (%s)", slug, res.status)
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.warning("Fehler beim Abrufen des Rezept-Details fuer %s: %s", slug, err)
            return None

    async def _fetch_recipes_cached(self, recipes_list, mealie_url, headers):
        """Return full recipe details, only re-fetching recipes that changed.

        Mealie's recipe list carries an update timestamp per recipe. Details
        are cached per slug and re-fetched only when that timestamp changes
        (or, if Mealie sends none, after RECIPE_CACHE_MAX_AGE).
        """
        now = dt_util.utcnow()
        semaphore = asyncio.Semaphore(5)
        wanted = {}
        to_fetch = []

        for summary in recipes_list:
            if not isinstance(summary, dict) or not summary.get("slug"):
                continue
            slug = summary["slug"]
            marker = summary.get("dateUpdated") or summary.get("updatedAt") or summary.get("updateAt")
            wanted[slug] = marker
            cached = self._recipe_cache.get(slug)
            if cached and (
                (marker and cached["marker"] == marker)
                or (not marker and now - cached["fetched"] < RECIPE_CACHE_MAX_AGE)
            ):
                continue
            to_fetch.append(slug)

        if to_fetch:
            fetched = await asyncio.gather(
                *[self._fetch_recipe_details(semaphore, slug, mealie_url, headers) for slug in to_fetch],
                return_exceptions=True,
            )
            for slug, details in zip(to_fetch, fetched):
                if isinstance(details, dict):
                    self._recipe_cache[slug] = {
                        "marker": wanted[slug],
                        "fetched": now,
                        "details": details,
                    }

        # Drop recipes that no longer exist in Mealie.
        for slug in list(self._recipe_cache):
            if slug not in wanted:
                del self._recipe_cache[slug]

        _LOGGER.debug(
            "Rezepte: %s im Cache, %s neu geladen", len(self._recipe_cache), len(to_fetch)
        )
        return [self._recipe_cache[slug]["details"] for slug in wanted if slug in self._recipe_cache]

    async def _fetch_mealplan(self, mealie_url, headers, today, window):
        """Fetch the meal plan and return (planned identifiers, window entries).

        Returns None if Mealie could not be reached, so the last known
        meal plan can be kept instead of silently showing an empty one.
        """
        mealplan_start, mealplan_end = window
        mealplan_url = (
            f"{mealie_url}/api/households/mealplans"
            f"?startTime={mealplan_start}&endTime={mealplan_end}&perPage=-1"
        )
        try:
            async with self.session.get(mealplan_url, headers=headers, timeout=REQUEST_TIMEOUT) as res:
                if res.status != 200:
                    _LOGGER.warning("Mealie-Speiseplan nicht abrufbar (HTTP %s)", res.status)
                    return None
                raw_data = await res.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Mealie-Speiseplan nicht abrufbar: %s", err)
            return None

        planned_identifiers = set()
        invalid_keywords = {"none", "null", "string", ""}
        selected_mealplan = []

        for plan in self._extract_mealplan_items(raw_data) or []:
            if not isinstance(plan, dict):
                continue
            plan_date = parse_mealplan_date(plan)
            if plan_date is None:
                continue

            if plan_date >= today:
                r_id = str(plan.get("recipeId") or "").strip().lower()
                if r_id not in invalid_keywords and len(r_id) > 5:
                    planned_identifiers.add(r_id)
                recipe_obj = plan.get("recipe")
                if isinstance(recipe_obj, dict):
                    for key in ("id", "slug"):
                        val = str(recipe_obj.get(key) or "").strip().lower()
                        if val not in invalid_keywords and len(val) > 2:
                            planned_identifiers.add(val)

            if not (mealplan_start <= plan_date <= mealplan_end):
                continue

            recipe_meta = self._extract_mealplan_recipe_meta(plan, mealie_url)
            selected_mealplan.append(
                {
                    "date": plan_date.isoformat(),
                    "dateLabel": plan_date.strftime("%d.%m.%Y"),
                    "weekday": WEEKDAY_NAMES_DE[plan_date.weekday()],
                    "entryType": str(plan.get("entryType", "meal")).strip(),
                    "recipeName": self._extract_recipe_name(plan),
                    "imageUrl": recipe_meta["imageUrl"],
                    "imageFallbackUrl": recipe_meta["imageFallbackUrl"],
                    "prepTime": recipe_meta["prepTime"],
                    "cookTime": recipe_meta["cookTime"],
                    "totalTime": recipe_meta["totalTime"],
                }
            )

        selected_mealplan.sort(key=lambda item: (item["date"], item["entryType"], item["recipeName"]))
        return planned_identifiers, selected_mealplan

    async def _fetch_grocy_object_map(self, grocy_url, headers, object_name, builder):
        """Fetch a Grocy object list and convert it with the given builder."""
        try:
            async with self.session.get(
                f"{grocy_url}/api/objects/{object_name}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as res:
                if res.status == 200:
                    return builder(self._extract_api_items(await res.json()))
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Grocy %s konnten nicht geladen werden: %s", object_name, err)
        return {}

    async def _async_update_data(self):
        """Fetch data from Grocy and Mealie and run the matching algorithm."""
        config_entry_data = self.hass.data[DOMAIN][self.entry_id]

        grocy_url = normalize_base_url(config_entry_data[CONF_GROCY_URL])
        mealie_url = normalize_base_url(config_entry_data[CONF_MEALIE_URL])
        grocy_headers = {"GROCY-API-KEY": config_entry_data[CONF_GROCY_TOKEN]}
        mealie_headers = {"Authorization": f"Bearer {config_entry_data[CONF_MEALIE_TOKEN]}"}

        ui_exclusions = config_entry_data.get("excluded_foods_list", [])
        basics_to_ignore = [item.lower() for item in ui_exclusions] if ui_exclusions else DEFAULT_BASICS

        # -----------------------------------------------------------------
        # 1. Mealie Speiseplan
        # -----------------------------------------------------------------
        today = dt_util.now().date()
        mealplan_start, mealplan_end, mealplan_mode, mealplan_label = self._resolve_mealplan_window(
            today, config_entry_data
        )
        mealplan_result = await self._fetch_mealplan(
            mealie_url, mealie_headers, today, (mealplan_start, mealplan_end)
        )
        if mealplan_result is not None:
            self._planned_identifiers, self.mealplan = mealplan_result
        self.mealplan_range = {
            "start": mealplan_start.isoformat(),
            "end": mealplan_end.isoformat(),
            "mode": mealplan_mode,
            "label": mealplan_label,
        }

        # -----------------------------------------------------------------
        # 2. Grocy Bestand
        # -----------------------------------------------------------------
        try:
            async with self.session.get(
                f"{grocy_url}/api/stock", headers=grocy_headers, timeout=REQUEST_TIMEOUT
            ) as res:
                if res.status != 200:
                    raise UpdateFailed(f"Grocy API Fehler: {res.status}")
                grocy_data = await res.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Verbindung zu Grocy fehlgeschlagen: {err}") from err

        quantity_unit_map, location_map, product_group_map, stock_entries = await asyncio.gather(
            self._fetch_grocy_object_map(
                grocy_url, grocy_headers, "quantity_units", self._build_quantity_unit_map
            ),
            self._fetch_grocy_object_map(grocy_url, grocy_headers, "locations", self._build_id_name_map),
            self._fetch_grocy_object_map(
                grocy_url, grocy_headers, "product_groups", self._build_id_name_map
            ),
            self._fetch_stock_entries(grocy_url, grocy_headers),
        )

        grocy_products_map = build_products_map(grocy_data, today)
        stock_items = []
        for item in grocy_data or []:
            stock_snapshot = self._extract_stock_snapshot(
                item, quantity_unit_map, location_map, product_group_map
            )
            if stock_snapshot:
                stock_snapshot["status"] = stock_status(item.get("best_before_date"), today)
                stock_items.append(stock_snapshot)
        stock_items.sort(key=lambda entry: entry["name"].lower())
        self.stock_items = stock_items

        product_locations = {}
        if stock_entries is None:
            location_semaphore = asyncio.Semaphore(10)
            location_results = await asyncio.gather(
                *[
                    self._fetch_location_entries(location_semaphore, location_id, grocy_url, grocy_headers)
                    for location_id in sorted(location_map)
                ],
                return_exceptions=True,
            )
            stock_entries = []
            for result in location_results:
                if isinstance(result, Exception):
                    continue
                location_id, rows = result
                stock_entries.extend(
                    {**row, "location_id": location_id} for row in rows if isinstance(row, dict)
                )

        for row in stock_entries:
            if not isinstance(row, dict):
                continue
            product_id = self._extract_product_id(row)
            if product_id is not None:
                product_locations.setdefault(product_id, []).append(row)

        self.inventory_items = self._build_inventory_items(
            stock_items, product_locations, location_map, today
        )
        self.inventory_locations = self._build_location_summaries(self.inventory_items)

        # -----------------------------------------------------------------
        # 3. Mealie Rezepte (mit Cache)
        # -----------------------------------------------------------------
        try:
            async with self.session.get(
                f"{mealie_url}/api/recipes?perPage=-1", headers=mealie_headers, timeout=REQUEST_TIMEOUT
            ) as res:
                if res.status != 200:
                    raise UpdateFailed(f"Mealie API Fehler: {res.status}")
                mealie_data = await res.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Verbindung zu Mealie fehlgeschlagen: {err}") from err

        recipes_list = mealie_data.get("items", []) if isinstance(mealie_data, dict) else []
        full_recipes = await self._fetch_recipes_cached(recipes_list, mealie_url, mealie_headers)

        # -----------------------------------------------------------------
        # 4. Matching
        # -----------------------------------------------------------------
        results = []
        for recipe in full_recipes:
            if not isinstance(recipe, dict):
                continue

            r_id = recipe.get("id")
            r_recipe_id = recipe.get("recipeId")
            r_slug = recipe.get("slug")
            if any(
                str(identifier).strip().lower() in self._planned_identifiers
                for identifier in (r_id, r_recipe_id, r_slug)
                if identifier
            ):
                continue

            analysis = analyze_recipe(recipe, grocy_products_map, basics_to_ignore)
            if not analysis["relevantTotal"] or not analysis["matchCount"]:
                continue

            results.append(
                {
                    "recipeId": str(r_recipe_id or r_id).strip(),
                    "recipeName": recipe.get("name", "Unbekanntes Rezept"),
                    "matchScore": analysis["matchScore"],
                    "matchCount": analysis["matchCount"],
                    "relevantTotal": analysis["relevantTotal"],
                    "matchingIngredients": analysis["matchingIngredients"],
                    "missingIngredients": analysis["missingIngredients"],
                    "basicIngredients": analysis["basicIngredients"],
                    "url": f"{mealie_url}/g/home/r/{r_slug or ''}",
                    "hasExpiring": analysis["hasExpiring"],
                }
            )

        results.sort(key=lambda x: x["matchScore"], reverse=True)
        return results


class MealieGrocyBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor that keeps large UI payloads out of Recorder history."""

    # The recipe, meal-plan and stock payloads are UI data and can become large.
    # Keep them available in the live state machine, but do not persist them in
    # Recorder history. This avoids the 16 KiB Recorder attribute limit and
    # unnecessary database growth.
    _unrecorded_attributes = frozenset({MATCH_ALL})
    # Names are shown as "<device name> <entity name>", e.g.
    # "Mealie Grocy Bridge Kochvorschläge". Entity ids stay unchanged
    # because they are stored in the entity registry.
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MealieGrocyBridgeCoordinator,
        integration_version: str,
    ) -> None:
        """Initialize common coordinator and version state."""
        super().__init__(coordinator)
        self._integration_version = integration_version
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name="Mealie Grocy Bridge",
            manufacturer="SniperWCW",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=integration_version or None,
        )


class MealieGrocySensor(MealieGrocyBaseSensor):
    """Expose recipe suggestions and meal planning data."""

    def __init__(
        self,
        coordinator: MealieGrocyBridgeCoordinator,
        entry_id: str,
        integration_version: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, integration_version)
        self._attr_unique_id = f"{entry_id}_suggestions"
        self._attr_name = "Kochvorschläge"
        self._attr_icon = "mdi:chef-hat"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "recipes": self.coordinator.data if self.coordinator.data else [],
            "mealplan": self.coordinator.mealplan,
            "mealplan_range": self.coordinator.mealplan_range,
            "integration_version": self._integration_version,
        }


class MealieGrocyInventorySensor(MealieGrocyBaseSensor):
    """Expose the Grocy inventory grouped by its current storage locations."""

    def __init__(
        self,
        coordinator: MealieGrocyBridgeCoordinator,
        entry_id: str,
        integration_version: str,
    ) -> None:
        """Initialize the inventory sensor."""
        super().__init__(coordinator, integration_version)
        self._attr_unique_id = f"{entry_id}_inventory"
        self._attr_name = "Bestand"
        self._attr_icon = "mdi:warehouse"

    @property
    def native_value(self) -> int:
        """Return the number of product/location combinations in stock."""
        return len(self.coordinator.inventory_items)

    @property
    def extra_state_attributes(self) -> dict:
        """Return inventory details and compact location summaries."""
        items = self.coordinator.inventory_items
        return {
            "items": items,
            "locations": self.coordinator.inventory_locations,
            "location_count": len(self.coordinator.inventory_locations),
            "product_count": len(
                {
                    item.get("product_id") or f"name:{item.get('name')}"
                    for item in items
                    if item.get("product_id") is not None or item.get("name")
                }
            ),
            "expiring_count": sum(item.get("status") == "expiring" for item in items),
            "expired_count": sum(item.get("status") == "expired" for item in items),
            "integration_version": self._integration_version,
        }


class MealieGrocyEmergencySupplySensor(MealieGrocyBaseSensor):
    """Expose a compact stock view for emergency-supply evaluation."""

    def __init__(
        self,
        coordinator: MealieGrocyBridgeCoordinator,
        entry_id: str,
        integration_version: str,
    ) -> None:
        """Initialize the emergency supply sensor."""
        super().__init__(coordinator, integration_version)
        self._attr_unique_id = f"{entry_id}_emergency_supply"
        self._attr_name = "Vorrat"
        self._attr_icon = "mdi:shield-check-outline"

    @property
    def native_value(self) -> int:
        """Return the number of usable products considered for emergency supply."""
        return sum(item.get("status") != "expired" for item in self.coordinator.stock_items)

    @property
    def extra_state_attributes(self) -> dict:
        """Return only fields required by the emergency-supply card."""
        compact_items = [
            {
                "name": item.get("name"),
                "amount": item.get("amount"),
                "unit": item.get("unit"),
                "status": item.get("status"),
                "best_before_date": item.get("best_before_date"),
                "product_group": item.get("product_group"),
                "calories": item.get("calories"),
                "location": item.get("location"),
            }
            for item in self.coordinator.stock_items
        ]
        return {
            "stock_items": compact_items,
            "total_count": len(compact_items),
            "expiring_count": sum(item.get("status") == "expiring" for item in compact_items),
            "expired_count": sum(item.get("status") == "expired" for item in compact_items),
            "integration_version": self._integration_version,
        }

"""The Mealie Grocy Bridge integration."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_MEALPLAN_SYNC_ENABLED,
    CONF_DAILY_MEALPLAN_SYNC_TIME,
    CONF_GROCY_TOKEN,
    CONF_GROCY_URL,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    CONF_MEALPLAN_SYNC_DAYS_AHEAD,
    CONF_MEALPLAN_SYNC_MODE,
    CONF_MEALPLAN_SYNC_WEEKDAY,
    CONF_TODO_ENTITY,
    DOMAIN,
    MEALPLAN_SYNC_MODE_DAILY,
    MEALPLAN_SYNC_MODE_WEEKLY,
)

_LOGGER = logging.getLogger(__name__)

CONF_EXCLUDED_FOODS = "excluded_foods"
URL_BASE = "/mealie_grocy_bridge_ui"
CARD_FILENAME = "mealie-grocy-card.js"
SYNCABLE_ENTRY_TYPES = {"lunch", "dinner"}
WEEKDAY_NAME_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _get_card_resource_url() -> str:
    """Build a cache-busted resource URL for the custom card."""
    manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
    version = "dev"
    try:
        with open(manifest_path, encoding="utf-8") as manifest_file:
            version = json.load(manifest_file).get("version", version)
    except Exception as err:
        _LOGGER.debug("Konnte Versionsnummer fuer Karten-Cachebuster nicht lesen: %s", err)
    return f"{URL_BASE}/{CARD_FILENAME}?v={version}"


def _get_entry_runtime(hass: HomeAssistant, entry_id: str) -> dict:
    """Return the runtime data for the active config entry."""
    return hass.data.get(DOMAIN, {}).get(entry_id, {})


def _normalize_list_item(text: str) -> str:
    """Normalize list items for duplicate comparison."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _coerce_time_value(value) -> tuple[int, int]:
    """Convert configured time values to hour and minute."""
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour), int(value.minute)

    text_value = str(value or "07:00").strip()
    parts = text_value.split(":")
    if len(parts) < 2:
        return 7, 0
    return int(parts[0]), int(parts[1])


def _parse_mealplan_entry_date(plan: dict) -> date | None:
    """Extract the calendar date from a mealplan entry."""
    if not isinstance(plan, dict):
        return None

    raw_value = plan.get("date") or plan.get("startTime") or plan.get("startDate")
    if not raw_value:
        return None

    text_value = str(raw_value).strip()
    if not text_value:
        return None

    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
    except ValueError:
        pass

    try:
        return datetime.strptime(text_value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _recipe_matches_mealplan_entry(
    recipe_details: dict, recipe_id: str | None, recipe_slug: str | None
) -> bool:
    """Validate that fetched recipe details match the meal plan entry."""
    if not isinstance(recipe_details, dict):
        return False

    fetched_id = str(recipe_details.get("id") or "").strip()
    fetched_slug = str(recipe_details.get("slug") or "").strip()
    expected_id = str(recipe_id or "").strip()
    expected_slug = str(recipe_slug or "").strip()

    if expected_id and fetched_id:
        return fetched_id == expected_id
    if expected_slug and fetched_slug:
        return fetched_slug == expected_slug
    return not expected_id and not expected_slug


def _build_grocy_products_map(grocy_data, _today):
    """Create a normalized lookup map for Grocy stock."""
    grocy_products_map = {}
    for item in (grocy_data or []):
        if isinstance(item, dict) and "product" in item:
            product_name = item.get("product", {}).get("name")
            if product_name:
                orig_name = str(product_name).strip()
                grocy_products_map[orig_name.lower()] = {
                    "orig_name": orig_name,
                    "regex": re.compile(r"\b" + re.escape(orig_name.lower()) + r"\b"),
                }
    return grocy_products_map


def _extract_missing_ingredients(recipe, grocy_products_map, basics_to_ignore):
    """Extract missing ingredients for one recipe using the existing matching heuristics."""
    all_ingredients = recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []
    relevant_ingredients = []

    for ingredient in all_ingredients:
        if not isinstance(ingredient, dict):
            continue
        display_text = (
            ingredient.get("display")
            or ingredient.get("note")
            or ingredient.get("originalText")
            or ""
        )
        text_low = str(display_text).lower()
        if not text_low:
            continue
        if any(basic in text_low for basic in basics_to_ignore):
            continue
        relevant_ingredients.append(ingredient)

    missing_ingredients = []
    for ingredient in relevant_ingredients:
        ing_original_text = (
            ingredient.get("display")
            or ingredient.get("note")
            or ingredient.get("originalText")
            or ""
        )
        ing_text_low = str(ing_original_text).lower()
        ing_words = [w for w in re.split(r"[\s,()./]+", ing_text_low) if len(w) > 2 and not w.isdigit()]

        found_product = None
        for stock_low, info in grocy_products_map.items():
            if any(nw in stock_low for nw in ["yumyum", "nudeln", "ramen", "reis"]):
                if any(fw in ing_text_low for fw in ["wings", "schenkel", "filet", "keulen"]):
                    continue
                if any(kw in stock_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                    if not any(kw in ing_text_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                        continue

            if info["regex"].search(ing_text_low):
                found_product = info
                break

        if not found_product:
            for stock_low, info in grocy_products_map.items():
                if any(nw in stock_low for nw in ["yumyum", "nudeln", "ramen", "reis"]):
                    if any(fw in ing_text_low for fw in ["wings", "schenkel", "filet", "keulen"]):
                        continue

                stock_words = [p.strip() for p in re.split(r"[\s\-,._()]+", stock_low) if len(p.strip()) > 2]
                if not stock_words:
                    continue

                if "chicken" in ing_words and "chicken" in stock_words:
                    if "wings" in ing_words and "wings" not in stock_words:
                        continue
                    if "nuggets" in ing_words and "nuggets" not in stock_words:
                        continue

                if any(nw in stock_low for nw in ["nudeln", "ramen", "yumyum", "reis"]):
                    if not any(nw in ing_text_low for nw in ["nudeln", "ramen", "suppe", "yumyum", "reis"]):
                        continue
                    if any(kw in stock_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                        if not any(kw in ing_text_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                            continue
                    if "wan-tan" in stock_low and "wan-tan" not in ing_text_low:
                        continue

                match_found = False
                for word in ing_words:
                    for stock_word in stock_words:
                        if (
                            word == stock_word
                            or word + "n" == stock_word
                            or word + "s" == stock_word
                            or word + "en" == stock_word
                            or stock_word + "n" == word
                            or stock_word + "s" == word
                        ):
                            found_product = info
                            match_found = True
                            break
                    if match_found:
                        break
                if match_found:
                    break

        if not found_product:
            cleaned_ingredient = str(ing_original_text).strip()
            if cleaned_ingredient:
                missing_ingredients.append(cleaned_ingredient[0].upper() + cleaned_ingredient[1:])

    return missing_ingredients


async def _fetch_todo_items(hass: HomeAssistant, todo_entity: str) -> list[dict]:
    """Fetch active items from the target to-do list."""
    try:
        response = await hass.services.async_call(
            "todo",
            "get_items",
            {"entity_id": todo_entity, "status": ["needs_action"]},
            blocking=True,
            return_response=True,
        )
    except Exception as err:
        _LOGGER.error("Konnte bestehende To-Do-Eintraege fuer %s nicht laden: %s", todo_entity, err)
        return []

    if not isinstance(response, dict):
        return []

    entity_response = response.get(todo_entity, {})
    return entity_response.get("items", []) if isinstance(entity_response, dict) else []


def _resolve_sync_target_dates(runtime_data: dict, now_date: date) -> list[date]:
    """Resolve the meal plan dates for the current sync run."""
    sync_mode = runtime_data.get(CONF_MEALPLAN_SYNC_MODE, MEALPLAN_SYNC_MODE_DAILY)
    if sync_mode == MEALPLAN_SYNC_MODE_WEEKLY:
        configured_weekday = str(runtime_data.get(CONF_MEALPLAN_SYNC_WEEKDAY, "sunday")).strip().lower()
        if now_date.weekday() != WEEKDAY_NAME_TO_INDEX.get(configured_weekday, 6):
            return []

        days_ahead = runtime_data.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7)
        try:
            days_ahead = int(days_ahead)
        except (TypeError, ValueError):
            days_ahead = 7
        days_ahead = max(1, min(days_ahead, 14))
        return [now_date + timedelta(days=offset) for offset in range(days_ahead)]

    return [now_date]


def _format_sync_range_label(target_dates: list[date]) -> str:
    """Build a human-readable label for sync logging and todo descriptions."""
    if not target_dates:
        return ""
    if len(target_dates) == 1:
        return target_dates[0].strftime("%d.%m.%Y")
    return f"{target_dates[0].strftime('%d.%m.%Y')} bis {target_dates[-1].strftime('%d.%m.%Y')}"


async def _run_mealplan_sync(hass: HomeAssistant, entry_id: str, target_dates: list[date]) -> None:
    """Sync missing ingredients from the configured meal plan dates to the todo list."""
    runtime_data = _get_entry_runtime(hass, entry_id)
    if not runtime_data or not target_dates:
        return

    mealie_url = runtime_data[CONF_MEALIE_URL].rstrip("/")
    if not mealie_url.startswith(("http://", "https://")):
        mealie_url = f"http://{mealie_url}"
    grocy_url = runtime_data[CONF_GROCY_URL].rstrip("/")
    if not grocy_url.startswith(("http://", "https://")):
        grocy_url = f"http://{grocy_url}"

    todo_entity = runtime_data.get(CONF_TODO_ENTITY)
    if not todo_entity:
        _LOGGER.warning("Essensplan-Sync uebersprungen: keine To-Do-Liste konfiguriert.")
        return

    session = async_get_clientsession(hass)
    mealie_headers = {"Authorization": f"Bearer {runtime_data[CONF_MEALIE_TOKEN]}"}
    grocy_headers = {"GROCY-API-KEY": runtime_data[CONF_GROCY_TOKEN]}
    basics_to_ignore = [item.lower() for item in runtime_data.get("excluded_foods_list", [])]
    target_date_set = set(target_dates)
    start_date = min(target_date_set).isoformat()
    end_date = max(target_date_set).isoformat()
    sync_range_label = _format_sync_range_label(target_dates)

    mealplan_url = (
        f"{mealie_url}/api/households/mealplans"
        f"?startTime={start_date}&endTime={end_date}&perPage=-1"
    )

    try:
        async with session.get(mealplan_url, headers=mealie_headers, timeout=15) as response:
            if response.status != 200:
                _LOGGER.error("Essensplan-Sync: Mealie-Speiseplan konnte nicht geladen werden (%s).", response.status)
                return
            mealplan_data = await response.json()
    except Exception as err:
        _LOGGER.error("Essensplan-Sync: Fehler beim Abrufen des Speiseplans: %s", err)
        return

    items = mealplan_data.get("items", mealplan_data) if isinstance(mealplan_data, dict) else mealplan_data
    matching_plans = []
    for plan in (items or []):
        if not isinstance(plan, dict):
            continue
        entry_type = str(plan.get("entryType", "")).strip().lower()
        plan_date = _parse_mealplan_entry_date(plan)
        if entry_type not in SYNCABLE_ENTRY_TYPES or plan_date not in target_date_set:
            continue
        matching_plans.append(plan)

    if not matching_plans:
        _LOGGER.info("Essensplan-Sync: kein Mittag- oder Abendessen fuer %s gefunden.", sync_range_label)
        return

    try:
        async with session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=15) as response:
            if response.status != 200:
                _LOGGER.error("Essensplan-Sync: Grocy-Bestand konnte nicht geladen werden (%s).", response.status)
                return
            grocy_data = await response.json()
    except Exception as err:
        _LOGGER.error("Essensplan-Sync: Fehler beim Abrufen des Grocy-Bestands: %s", err)
        return

    grocy_products_map = _build_grocy_products_map(grocy_data, min(target_date_set))
    missing_ingredients = []

    for plan in matching_plans:
        recipe_obj = plan.get("recipe")
        recipe_id = str(
            plan.get("recipeId") or (recipe_obj.get("id") if isinstance(recipe_obj, dict) else "") or ""
        ).strip() or None
        recipe_slug = str(
            (recipe_obj.get("slug") if isinstance(recipe_obj, dict) else "") or ""
        ).strip() or None
        recipe_name = (
            recipe_obj.get("name")
            if isinstance(recipe_obj, dict) and recipe_obj.get("name")
            else plan.get("title") or plan.get("text") or "Unbekanntes Rezept"
        )
        recipe_identifier = recipe_id or recipe_slug
        if not recipe_identifier:
            _LOGGER.warning(
                "Essensplan-Sync: Mealplan-Eintrag '%s' hat weder Recipe-ID noch Slug und wird uebersprungen.",
                recipe_name,
            )
            continue

        try:
            async with session.get(
                f"{mealie_url}/api/recipes/{recipe_identifier}",
                headers=mealie_headers,
                timeout=15,
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Essensplan-Sync: Rezept %s konnte nicht geladen werden (%s).", recipe_identifier, response.status)
                    continue
                recipe_details = await response.json()
        except Exception as err:
            _LOGGER.warning("Essensplan-Sync: Fehler beim Laden von Rezept %s: %s", recipe_identifier, err)
            continue

        if not _recipe_matches_mealplan_entry(recipe_details, recipe_id, recipe_slug):
            _LOGGER.warning(
                "Essensplan-Sync: Rezept-Mismatch fuer '%s'. Erwartet id=%s slug=%s, erhalten id=%s slug=%s.",
                recipe_name,
                recipe_id,
                recipe_slug,
                recipe_details.get("id"),
                recipe_details.get("slug"),
            )
            continue

        missing_ingredients.extend(
            _extract_missing_ingredients(recipe_details, grocy_products_map, basics_to_ignore)
        )

    if not missing_ingredients:
        _LOGGER.info("Essensplan-Sync: keine fehlenden Zutaten fuer %s gefunden.", sync_range_label)
        return

    existing_items = await _fetch_todo_items(hass, todo_entity)
    existing_normalized = {
        _normalize_list_item(item.get("summary") or item.get("item") or "")
        for item in existing_items
        if isinstance(item, dict)
    }

    normalized_to_add = set()
    added_count = 0
    description = f"fuer Essensplan {sync_range_label}"

    for ingredient in missing_ingredients:
        normalized = _normalize_list_item(ingredient)
        if not normalized or normalized in existing_normalized or normalized in normalized_to_add:
            continue

        try:
            await hass.services.async_call(
                "todo",
                "add_item",
                {"entity_id": todo_entity, "item": ingredient, "description": description},
                blocking=True,
            )
            normalized_to_add.add(normalized)
            added_count += 1
        except Exception as err:
            _LOGGER.error("Essensplan-Sync: Fehler beim Hinzufuegen von '%s' zu %s: %s", ingredient, todo_entity, err)

    _LOGGER.info(
        "Essensplan-Sync abgeschlossen: %s neue Eintraege fuer %s zur Liste %s hinzugefuegt.",
        added_count,
        sync_range_label,
        todo_entity,
    )


def _setup_daily_mealplan_sync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register or remove the meal plan sync based on the current config."""
    runtime_data = _get_entry_runtime(hass, entry.entry_id)
    if not runtime_data:
        return

    unsubscribe = runtime_data.pop("daily_sync_unsub", None)
    if unsubscribe:
        unsubscribe()

    if not runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED):
        return

    hour, minute = _coerce_time_value(runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_TIME, "07:00"))

    async def _handle_daily_sync(_now):
        now_date = dt_util.now().date()
        target_dates = _resolve_sync_target_dates(runtime_data, now_date)
        if not target_dates:
            return
        await _run_mealplan_sync(hass, entry.entry_id, target_dates)

    runtime_data["daily_sync_unsub"] = async_track_time_change(
        hass,
        _handle_daily_sync,
        hour=hour,
        minute=minute,
        second=0,
    )


def _prepare_runtime_config(config: dict) -> dict:
    """Normalize UI config into runtime-friendly values."""
    exclusions_raw = config.get(CONF_EXCLUDED_FOODS, "")
    excluded_foods_list = [item.strip() for item in exclusions_raw.split(",") if item.strip()]

    try:
        config[CONF_MEALPLAN_SYNC_DAYS_AHEAD] = int(config.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7))
    except (TypeError, ValueError):
        config[CONF_MEALPLAN_SYNC_DAYS_AHEAD] = 7

    return {**config, "excluded_foods_list": excluded_foods_list}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config = {**entry.data, **entry.options}
    hass.data[DOMAIN][entry.entry_id] = _prepare_runtime_config(config)
    _setup_daily_mealplan_sync(hass, entry)

    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        if os.path.isdir(frontend_dir):
            if "mealie_grocy_bridge_frontend" not in hass.http.app.router:
                hass.http.app.router.add_static(
                    URL_BASE,
                    frontend_dir,
                    name="mealie_grocy_bridge_frontend",
                )

            if "frontend" in hass.data and "lovelace" in hass.data["frontend"]:
                lovelace = hass.data["frontend"]["lovelace"]
                if hasattr(lovelace, "resources"):
                    resources = lovelace.resources
                    card_url = _get_card_resource_url()
                    legacy_card_url = f"{URL_BASE}/{CARD_FILENAME}"

                    items = await resources.async_items()
                    existing_urls = {item.get("url") for item in items}
                    if legacy_card_url in existing_urls and card_url not in existing_urls:
                        for item in items:
                            if item.get("url") == legacy_card_url and item.get("id") is not None:
                                await resources.async_delete_item(item["id"])
                    if card_url not in existing_urls:
                        await resources.async_create_item({"url": card_url, "type": "module"})
        else:
            _LOGGER.warning("Frontend-Verzeichnis existiert nicht: %s", frontend_dir)
    except Exception as frontend_err:
        _LOGGER.error("Fehler bei der Frontend-Registrierung der Custom Card: %s", frontend_err)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    def get_recipe_by_index(index: int):
        """Return one recipe from the coordinator by its UI index."""
        runtime_data = _get_entry_runtime(hass, entry.entry_id)
        coordinator = runtime_data.get("coordinator")
        if not coordinator or not coordinator.data:
            _LOGGER.warning("Coordinator noch nicht bereit oder keine Rezepte geladen.")
            return None
        try:
            if 0 <= index < len(coordinator.data):
                return coordinator.data[index]
        except Exception as err:
            _LOGGER.error("Fehler beim Auslesen des Rezept-Index: %s", err)
        return None

    async def handle_add_missing_ingredients(call: ServiceCall):
        """Add missing ingredients of one recipe to the configured to-do list."""
        recipe_index = int(call.data.get("recipe_index", 0))
        recipe = get_recipe_by_index(recipe_index)
        if not recipe:
            _LOGGER.error("Zutaten-Export fehlgeschlagen: Kein Rezept unter Index %s gefunden", recipe_index)
            return

        missing_ingredients = recipe.get("missingIngredients", [])
        if not missing_ingredients:
            _LOGGER.info("Keine fehlenden Zutaten fuer '%s' vorhanden.", recipe.get("recipeName"))
            return

        current_config = _get_entry_runtime(hass, entry.entry_id)
        todo_entity = current_config.get(CONF_TODO_ENTITY) or "todo.stuttgart"
        added_count = 0

        for ingredient in missing_ingredients:
            if not ingredient:
                continue
            try:
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {
                        "entity_id": todo_entity,
                        "item": str(ingredient),
                        "description": f"fuer {recipe.get('recipeName')}",
                    },
                    blocking=True,
                )
                added_count += 1
            except Exception as err:
                _LOGGER.error("Fehler beim Hinzufuegen von '%s' zur To-Do-Liste '%s': %s", ingredient, todo_entity, err)

        if added_count > 0:
            try:
                friendly_list_name = todo_entity.split(".")[-1].replace("_", " ").title()
                await hass.services.async_call(
                    "notify",
                    "notify",
                    {
                        "title": "Einkaufsliste aktualisiert",
                        "message": (
                            f"{added_count} fehlende Zutat(en) fuer '{recipe.get('recipeName')}' "
                            f"wurden zur Liste '{friendly_list_name}' hinzugefuegt."
                        ),
                    },
                )
            except Exception as notify_err:
                _LOGGER.error("Konnte Push-Nachricht fuer Einkaufsliste nicht senden: %s", notify_err)

    async def handle_set_to_next_free_day(call: ServiceCall):
        """Find the next free day or use the selected date and schedule the recipe."""
        recipe_index = int(call.data.get("recipe_index", 0))
        recipe = get_recipe_by_index(recipe_index)
        if not recipe:
            _LOGGER.error("Planung fehlgeschlagen: Kein Rezept unter Index %s gefunden", recipe_index)
            return

        recipe_id = recipe.get("recipeId")
        recipe_name = recipe.get("recipeName", "Unbekanntes Rezept")

        current_config = _get_entry_runtime(hass, entry.entry_id)
        mealie_url = current_config[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"

        mealie_headers = {"Authorization": f"Bearer {current_config[CONF_MEALIE_TOKEN]}"}
        selected_date = call.data.get("selected_date")
        entry_type = str(call.data.get("entry_type", "dinner")).strip().lower() or "dinner"
        session = async_get_clientsession(hass)

        today = dt_util.now().date()
        end_date = today + timedelta(days=30)
        plan_url = f"{mealie_url}/api/households/mealplans?startTime={today}&endTime={end_date}&perPage=-1"

        try:
            async with session.get(plan_url, headers=mealie_headers, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.error("Konnte Speiseplan von Mealie nicht abrufen. Status: %s", resp.status)
                    return

                mealplans = await resp.json()
                items = mealplans.get("items", mealplans) if isinstance(mealplans, dict) else mealplans
                blocked_days = set()
                for plan in items or []:
                    if not isinstance(plan, dict):
                        continue
                    if str(plan.get("entryType", "")).strip().lower() != entry_type:
                        continue
                    plan_date = _parse_mealplan_entry_date(plan)
                    if plan_date:
                        blocked_days.add(plan_date.isoformat())

            if selected_date:
                try:
                    target_date = datetime.strptime(str(selected_date), "%Y-%m-%d").date()
                except ValueError:
                    _LOGGER.error("Ungueltiges Datum '%s' fuer Rezeptplanung", selected_date)
                    return
            else:
                target_date = today
                for _ in range(30):
                    if target_date.isoformat() not in blocked_days:
                        break
                    target_date += timedelta(days=1)

            payload = {"date": str(target_date), "entryType": entry_type, "recipeId": recipe_id}
            async with session.post(
                f"{mealie_url}/api/households/mealplans",
                headers=mealie_headers,
                json=payload,
                timeout=10,
            ) as post_resp:
                if post_resp.status in [200, 201]:
                    try:
                        await hass.services.async_call(
                            "notify",
                            "notify",
                            {
                                "title": "Mealie Speiseplan",
                                "message": (
                                    f'"{recipe_name}" wurde erfolgreich fuer den '
                                    f'{target_date.strftime("%d.%m.%Y")} als {entry_type} eingetragen.'
                                ),
                            },
                        )
                    except Exception as notify_err:
                        _LOGGER.error("Konnte Push-Nachricht nicht senden: %s", notify_err)

                    coordinator = _get_entry_runtime(hass, entry.entry_id).get("coordinator")
                    if coordinator:
                        hass.async_create_task(coordinator.async_refresh())
                else:
                    _LOGGER.error("Mealie API verweigerte das Eintragen: %s", await post_resp.text())
        except Exception as err:
            _LOGGER.error("Fehler bei der Kommunikation mit der Mealie-Speiseplan-API: %s", err)

    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)
    hass.services.async_register(DOMAIN, "set_to_next_free_day", handle_set_to_next_free_day)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    hass.services.async_remove(DOMAIN, "add_missing_ingredients")
    hass.services.async_remove(DOMAIN, "set_to_next_free_day")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        runtime_data = hass.data[DOMAIN].pop(entry.entry_id)
        unsubscribe = runtime_data.get("daily_sync_unsub")
        if unsubscribe:
            unsubscribe()

    return unload_ok

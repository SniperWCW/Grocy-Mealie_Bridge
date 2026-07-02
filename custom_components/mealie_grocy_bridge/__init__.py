"""The Mealie Grocy Bridge integration.

Diese Datei initialisiert die Integration, verarbeitet die Konfiguration aus der UI
und stellt die beiden zentralen Home Assistant Dienste (Services) bereit.
"""
import logging
import os
import json
import re
#import aiohttp
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

# Importe der Konstanten aus der lokalen const.py
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,  # KORREKTUR: War zuvor nicht importiert!
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_TODO_ENTITY,  # Enthält die Entity-ID der in der UI gewählten To-Do-Liste
    CONF_DAILY_MEALPLAN_SYNC_ENABLED,
    CONF_DAILY_MEALPLAN_SYNC_TIME,
)

# Logger-Instanz für Fehlermeldungen und Status-Infos im Home Assistant Log
_LOGGER = logging.getLogger(__name__)
CONF_EXCLUDED_FOODS = "excluded_foods"

URL_BASE = "/mealie_grocy_bridge_ui"
CARD_FILENAME = "mealie-grocy-card.js"


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


def _parse_mealplan_entry_date(plan: dict):
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


def _build_grocy_products_map(grocy_data, today):
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
        display_text = ingredient.get("display") or ingredient.get("note") or ingredient.get("originalText") or ""
        text_low = str(display_text).lower()
        if not text_low:
            continue
        if any(basic in text_low for basic in basics_to_ignore):
            continue
        relevant_ingredients.append(ingredient)

    missing_ingredients = []

    for ingredient in relevant_ingredients:
        ing_original_text = ingredient.get("display") or ingredient.get("note") or ingredient.get("originalText") or ""
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
            {
                "entity_id": todo_entity,
                "status": ["needs_action"],
            },
            blocking=True,
            return_response=True,
        )
    except Exception as err:
        _LOGGER.error("Konnte bestehende To-Do-Einträge für %s nicht laden: %s", todo_entity, err)
        return []

    if not isinstance(response, dict):
        return []

    entity_response = response.get(todo_entity, {})
    return entity_response.get("items", []) if isinstance(entity_response, dict) else []


async def _run_daily_mealplan_sync(hass: HomeAssistant, entry_id: str) -> None:
    """Sync missing ingredients from today's lunch and dinner meal plan to the todo list."""
    runtime_data = _get_entry_runtime(hass, entry_id)
    if not runtime_data:
        return

    mealie_url = runtime_data[CONF_MEALIE_URL].rstrip("/")
    if not mealie_url.startswith(("http://", "https://")):
        mealie_url = f"http://{mealie_url}"
    grocy_url = runtime_data[CONF_GROCY_URL].rstrip("/")
    if not grocy_url.startswith(("http://", "https://")):
        grocy_url = f"http://{grocy_url}"

    todo_entity = runtime_data.get(CONF_TODO_ENTITY)
    if not todo_entity:
        _LOGGER.warning("Täglicher Essensplan-Sync übersprungen: keine To-Do-Liste konfiguriert.")
        return

    session = async_get_clientsession(hass)
    today = dt_util.now().date()
    today_str = today.isoformat()
    mealie_headers = {"Authorization": f"Bearer {runtime_data[CONF_MEALIE_TOKEN]}"}
    grocy_headers = {"GROCY-API-KEY": runtime_data[CONF_GROCY_TOKEN]}
    basics_to_ignore = [item.lower() for item in runtime_data.get("excluded_foods_list", [])]

    mealplan_url = f"{mealie_url}/api/households/mealplans?startTime={today_str}&endTime={today_str}&perPage=-1"

    try:
        async with session.get(mealplan_url, headers=mealie_headers, timeout=15) as response:
            if response.status != 200:
                _LOGGER.error("Täglicher Essensplan-Sync: Mealie-Speiseplan konnte nicht geladen werden (%s).", response.status)
                return
            mealplan_data = await response.json()
    except Exception as err:
        _LOGGER.error("Täglicher Essensplan-Sync: Fehler beim Abrufen des Speiseplans: %s", err)
        return

    items = mealplan_data.get("items", mealplan_data) if isinstance(mealplan_data, dict) else mealplan_data
    todays_plans = []
    skipped_plans = 0
    for plan in (items or []):
        if not isinstance(plan, dict):
            continue

        entry_type = str(plan.get("entryType", "")).strip().lower()
        plan_date = _parse_mealplan_entry_date(plan)

        if entry_type not in {"lunch", "dinner"}:
            continue
        if plan_date != today:
            skipped_plans += 1
            continue

        todays_plans.append(plan)

    if not todays_plans:
        _LOGGER.info("Täglicher Essensplan-Sync: kein Mittag- oder Abendessen für %s gefunden.", today_str)
        return

    _LOGGER.info(
        "Taeglicher Essensplan-Sync: %s passende Essensplan-Eintraege fuer %s gefunden (%s weitere Lunch/Dinner-Eintraege mit anderem Datum ignoriert).",
        len(todays_plans),
        today_str,
        skipped_plans,
    )

    try:
        async with session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=15) as response:
            if response.status != 200:
                _LOGGER.error("Täglicher Essensplan-Sync: Grocy-Bestand konnte nicht geladen werden (%s).", response.status)
                return
            grocy_data = await response.json()
    except Exception as err:
        _LOGGER.error("Täglicher Essensplan-Sync: Fehler beim Abrufen des Grocy-Bestands: %s", err)
        return

    grocy_products_map = _build_grocy_products_map(grocy_data, today)
    missing_ingredients = []

    for plan in todays_plans:
        recipe_obj = plan.get("recipe")
        recipe_slug = recipe_obj.get("slug") if isinstance(recipe_obj, dict) else None
        recipe_name = (
            recipe_obj.get("name")
            if isinstance(recipe_obj, dict) and recipe_obj.get("name")
            else plan.get("title") or plan.get("text") or "Unbekanntes Rezept"
        )
        entry_type = str(plan.get("entryType", "")).strip().lower()
        if not recipe_slug:
            _LOGGER.warning(
                "Taeglicher Essensplan-Sync: Mealplan-Eintrag '%s' (%s) hat keinen Recipe-Slug und wird uebersprungen.",
                recipe_name,
                entry_type,
            )
            continue

        try:
            async with session.get(f"{mealie_url}/api/recipes/{recipe_slug}", headers=mealie_headers, timeout=15) as response:
                if response.status != 200:
                    _LOGGER.warning("Täglicher Essensplan-Sync: Rezept %s konnte nicht geladen werden (%s).", recipe_slug, response.status)
                    continue
                recipe_details = await response.json()
        except Exception as err:
            _LOGGER.warning("Täglicher Essensplan-Sync: Fehler beim Laden von Rezept %s: %s", recipe_slug, err)
            continue

        recipe_missing_ingredients = _extract_missing_ingredients(
            recipe_details, grocy_products_map, basics_to_ignore
        )
        _LOGGER.info(
            "Taeglicher Essensplan-Sync: verwende '%s' (%s, slug=%s) mit %s fehlenden Zutaten.",
            recipe_name,
            entry_type,
            recipe_slug,
            len(recipe_missing_ingredients),
        )
        missing_ingredients.extend(recipe_missing_ingredients)

    if not missing_ingredients:
        _LOGGER.info("Täglicher Essensplan-Sync: keine fehlenden Zutaten für %s gefunden.", today_str)
        return

    existing_items = await _fetch_todo_items(hass, todo_entity)
    existing_normalized = {
        _normalize_list_item(item.get("summary") or item.get("item") or "")
        for item in existing_items
        if isinstance(item, dict)
    }

    normalized_to_add = set()
    added_count = 0

    for ingredient in missing_ingredients:
        normalized = _normalize_list_item(ingredient)
        if not normalized or normalized in existing_normalized or normalized in normalized_to_add:
            continue

        try:
            await hass.services.async_call(
                "todo",
                "add_item",
                {
                    "entity_id": todo_entity,
                    "item": ingredient,
                    "description": f"für Essensplan {today.strftime('%d.%m.%Y')}",
                },
                blocking=True,
            )
            normalized_to_add.add(normalized)
            added_count += 1
        except Exception as err:
            _LOGGER.error("Täglicher Essensplan-Sync: Fehler beim Hinzufügen von '%s' zu %s: %s", ingredient, todo_entity, err)

    _LOGGER.info(
        "Täglicher Essensplan-Sync abgeschlossen: %s neue Einträge zur Liste %s hinzugefügt.",
        added_count,
        todo_entity,
    )


def _setup_daily_mealplan_sync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register or remove the daily meal plan sync based on the current config."""
    runtime_data = _get_entry_runtime(hass, entry.entry_id)
    if not runtime_data:
        return

    unsubscribe = runtime_data.pop("daily_sync_unsub", None)
    if unsubscribe:
        unsubscribe()

    if not runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED):
        return

    hour, minute = _coerce_time_value(runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_TIME, "07:00"))

    async def _handle_daily_sync(now):
        await _run_daily_mealplan_sync(hass, entry.entry_id)

    runtime_data["daily_sync_unsub"] = async_track_time_change(
        hass,
        _handle_daily_sync,
        hour=hour,
        minute=minute,
        second=0,
    )

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird von HA aufgerufen, wenn die Integration geladen oder gestartet wird.

    Hier wird die Konfiguration eingelesen und die Dienste werden registriert.
    """
    # Sicherstellen, dass das Speicher-Verzeichnis für unsere Integration im HA-Core existiert
    hass.data.setdefault(DOMAIN, {})
    
    # Kombiniert die Ersteinrichtung (entry.data) mit späteren UI-Änderungen (entry.options)
    config = {**entry.data, **entry.options}
    
    # Ausgelesene, per Komma getrennte Ausschlussliste aus der UI in eine saubere Python-Liste wandeln
    exclusions_raw = config.get(CONF_EXCLUDED_FOODS, "")
    excluded_foods_list = [item.strip() for item in exclusions_raw.split(",") if item.strip()]

    # Die bereinigte Konfiguration im globalen HA-Datenobjekt unter der eindeutigen Entry-ID ablegen
    hass.data[DOMAIN][entry.entry_id] = {
        **config,
        "excluded_foods_list": excluded_foods_list
    }

    _setup_daily_mealplan_sync(hass, entry)

    # -----------------------------------------------------------------
    # FRONTEND: Automatische Registrierung der Custom Card
    # -----------------------------------------------------------------
    try:
        # 1. Statischen Pfad für das Frontend-Verzeichnis registrieren
        frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        if os.path.isdir(frontend_dir):
            _LOGGER.info("Registriere statischen Pfad %s für %s", URL_BASE, frontend_dir)
            
            if "mealie_grocy_bridge_frontend" not in hass.http.app.router:
                hass.http.app.router.add_static(
                    URL_BASE,
                    frontend_dir,
                    name="mealie_grocy_bridge_frontend",
                )
            
            # 2. Lovelace-Ressourcen-Datenbank anpassen, falls das Frontend aktiv ist
            if "frontend" in hass.data and "lovelace" in hass.data["frontend"]:
                lovelace = hass.data["frontend"]["lovelace"]
                if hasattr(lovelace, "resources"):
                    resources = lovelace.resources
                    card_url = _get_card_resource_url()
                    legacy_card_url = f"{URL_BASE}/{CARD_FILENAME}"
                    
                    # Verhindert doppelte Einträge bei Neustarts
                    #if not any(r.get("url") == card_url for r in resources.async_items()):
                    items = await resources.async_items()
                    existing_urls = {r.get("url") for r in items}
                    if legacy_card_url in existing_urls and card_url not in existing_urls:
                        for item in items:
                            if item.get("url") == legacy_card_url and item.get("id") is not None:
                                await resources.async_delete_item(item["id"])
                    if card_url not in existing_urls:
                        _LOGGER.info("Registriere Mealie-Grocy Custom Card im Frontend...")
                        # await resources.async_create_item({
                        #     "res_type": "module",
                        #     "url": card_url
                        await resources.async_create_item({
                            "url": card_url,
                            "type": "module"
                        })
        else:
            _LOGGER.warning("Frontend-Verzeichnis existiert nicht: %s", frontend_dir)
    except Exception as frontend_err:
        _LOGGER.error("Fehler bei der Frontend-Registrierung der Custom Card: %s", frontend_err)

    # Registriert einen Listener, der feuert, wenn der Nutzer die Optionen in der UI speichert
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # -----------------------------------------------------------------
    # HELPER: Holt Rezepte sicher aus dem Daten-Coordinator
    # -----------------------------------------------------------------
    def get_recipe_by_index(index: int):
        """Hilfsfunktion, um anhand eines numerischen Index das passende Rezept aus dem Coordinator zu ziehen."""
        runtime_data = _get_entry_runtime(hass, entry.entry_id)
        coordinator = runtime_data.get("coordinator")
        if not coordinator or not coordinator.data:
            _LOGGER.warning("Coordinator noch nicht bereit oder keine Rezepte geladen.")
            return None
        try:
            # Überprüfen, ob der übergebene Index innerhalb der Array-Grenzen liegt
            if 0 <= index < len(coordinator.data):
                return coordinator.data[index]
        except Exception as err:
            _LOGGER.error("Fehler beim Auslesen des Rezept-Index: %s", err)
        return None

    # =====================================================================
    # DIENST 1: Fehlende Zutaten via INDEX auf die To-Do-Liste setzen
    # =====================================================================
    async def handle_add_missing_ingredients(call: ServiceCall):
        """Liest fehlende Zutaten eines Rezept-Index aus und schickt sie an die konfigurierte To-Do-Liste."""
        recipe_index = int(call.data.get("recipe_index", 0))
        recipe = get_recipe_by_index(recipe_index)
        
        if not recipe:
            _LOGGER.error("Zutaten-Export fehlgeschlagen: Kein Rezept unter Index %s gefunden", recipe_index)
            return

        missing_ingredients = recipe.get("missingIngredients", [])
        if not missing_ingredients:
            _LOGGER.info("Keine fehlenden Zutaten für '%s' vorhanden.", recipe.get("recipeName"))
            return

        current_config = _get_entry_runtime(hass, entry.entry_id)
        todo_entity = current_config.get(CONF_TODO_ENTITY)

        if not todo_entity:
            _LOGGER.warning("Keine To-Do-Liste in den Integrations-Optionen ausgewählt! Nutze Standardliste 'todo.stuttgart'.")
            todo_entity = "todo.stuttgart"

        _LOGGER.info("Füge fehlende Zutaten für '%s' zur To-Do-Liste '%s' hinzu: %s", recipe.get("recipeName"), todo_entity, missing_ingredients)

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
                        "description": f"für {recipe.get('recipeName')}"
                    },
                    blocking=True
                )
                added_count += 1  
            except Exception as err:
                _LOGGER.error("Fehler beim Hinzufügen von '%s' zur To-Do-Liste '%s': %s", ingredient, todo_entity, err)

        if added_count > 0:
            try:
                friendly_list_name = todo_entity.split(".")[-1].replace("_", " ").title()
                await hass.services.async_call(
                    "notify",
                    "notify",
                    {
                        "title": "🛒 Einkaufsliste aktualisiert",
                        "message": f"{added_count} fehlende Zutat(en) für '{recipe.get('recipeName')}' wurden zur Liste '{friendly_list_name}' hinzugefügt!"
                    }
                )
                _LOGGER.info("Erfolgreich Push-Nachricht für hinzugefügte Zutaten gesendet.")
            except Exception as notify_err:
                _LOGGER.error("Konnte Push-Nachricht für Einkaufsliste nicht senden: %s", notify_err)

    # =====================================================================
    # DIENST 2: Rezept via INDEX auf den nächsten freien Tag setzen + Notify
    # =====================================================================
    async def handle_set_to_next_free_day(call: ServiceCall):
        """Findet den nächsten freien Tag bei Mealie anhand des Rezept-Index und bucht ihn."""
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
            
        mealie_token = current_config[CONF_MEALIE_TOKEN]
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}
        selected_date = call.data.get("selected_date")
        entry_type = str(call.data.get("entry_type", "dinner")).strip().lower() or "dinner"
        
        session = async_get_clientsession(hass)

        today = datetime.now().date()
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
                for plan in items:
                    if plan.get("entryType") == entry_type:
                        plan_date = plan.get("date")
                        if plan_date:
                            blocked_days.add(plan_date.split("T")[0])

            if selected_date:
                try:
                    target_date = datetime.strptime(str(selected_date), "%Y-%m-%d").date()
                except ValueError:
                    _LOGGER.error("Ungültiges Datum '%s' für Rezeptplanung", selected_date)
                    return
            else:
                target_date = today
                for _ in range(30):
                    if str(target_date) not in blocked_days:
                        break
                    target_date += timedelta(days=1)
            
            payload = {
                "date": str(target_date),
                "entryType": entry_type,
                "recipeId": recipe_id
            }
            
            post_url = f"{mealie_url}/api/households/mealplans"
            async with session.post(post_url, headers=mealie_headers, json=payload, timeout=10) as post_resp:
                if post_resp.status in [200, 201]:
                    _LOGGER.info("Erfolgreich '%s' bei Mealie für den %s geplant", recipe_name, target_date)
                    
                    try:
                        await hass.services.async_call(
                            "notify",
                            "notify",
                            {
                                "title": "🍳 Mealie Speiseplan",
                                "message": f'"{recipe_name}" wurde erfolgreich für den {target_date.strftime("%d.%m.%Y")} als {entry_type} eingetragen!'
                            }
                        )
                    except Exception as notify_err:
                        _LOGGER.error("Konnte Push-Nachricht nicht senden: %s", notify_err)

                    coordinator = _get_entry_runtime(hass, entry.entry_id).get("coordinator")
                    if coordinator:
                        _LOGGER.info("Triggere sofortigen Sensor-Refresh...")
                        hass.async_create_task(coordinator.async_refresh())
                else:
                    error_text = await post_resp.text()
                    _LOGGER.error("Mealie API verweigerte das Eintragen: %s", error_text)

        except Exception as err:
            _LOGGER.error("Fehler bei der Kommunikation mit der Mealie-Speiseplan-API: %s", err)

    # Registrierung im Core
    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)
    hass.services.async_register(DOMAIN, "set_to_next_free_day", handle_set_to_next_free_day)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird aufgerufen, wenn der Nutzer die Integrationsoptionen in der HA-UI ändert."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration gelöscht oder deaktiviert wird."""
    #unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    hass.services.async_remove(DOMAIN, "add_missing_ingredients")
    hass.services.async_remove(DOMAIN, "set_to_next_free_day")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])

    if unload_ok:
        runtime_data = hass.data[DOMAIN].pop(entry.entry_id)
        unsubscribe = runtime_data.get("daily_sync_unsub")
        if unsubscribe:
            unsubscribe()

    return unload_ok

"""The Mealie Grocy Bridge integration.

Diese Datei initialisiert die Integration, verarbeitet die Konfiguration aus der UI
und stellt die beiden zentralen Home Assistant Dienste (Services) bereit.
"""
import logging
import os
#import aiohttp
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Importe der Konstanten aus der lokalen const.py
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,  # KORREKTUR: War zuvor nicht importiert!
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_TODO_ENTITY,  # Enthält die Entity-ID der in der UI gewählten To-Do-Liste
)

# Logger-Instanz für Fehlermeldungen und Status-Infos im Home Assistant Log
_LOGGER = logging.getLogger(__name__)
CONF_EXCLUDED_FOODS = "excluded_foods"

URL_BASE = "/mealie_grocy_bridge_ui"
CARD_FILENAME = "mealie-grocy-card.js"

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

    # -----------------------------------------------------------------
    # FRONTEND: Automatische Registrierung der Custom Card
    # -----------------------------------------------------------------
    try:
        # 1. Statischen Pfad für das Frontend-Verzeichnis registrieren
        frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        if os.path.isdir(frontend_dir):
            _LOGGER.info("Registriere statischen Pfad %s für %s", URL_BASE, frontend_dir)
            
            hass.http.app.router.add_static(URL_BASE, frontend_dir, name="mealie_grocy_bridge_frontend")
            
            # 2. Lovelace-Ressourcen-Datenbank anpassen, falls das Frontend aktiv ist
            if "frontend" in hass.data and "lovelace" in hass.data["frontend"]:
                lovelace = hass.data["frontend"]["lovelace"]
                if hasattr(lovelace, "resources"):
                    resources = lovelace.resources
                    card_url = f"{URL_BASE}/{CARD_FILENAME}"
                    
                    # Verhindert doppelte Einträge bei Neustarts
                    #if not any(r.get("url") == card_url for r in resources.async_items()):
                    items = await resources.async_items()
                    if not any(r.get("url") == card_url for r in items):
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
        coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
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

        current_config = hass.data[DOMAIN][entry.entry_id]
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

        current_config = hass.data[DOMAIN][entry.entry_id]
        mealie_url = current_config[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"
            
        mealie_token = current_config[CONF_MEALIE_TOKEN]
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}
        
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
                    if plan.get("entryType") == "dinner":
                        plan_date = plan.get("date")
                        if plan_date:
                            blocked_days.add(plan_date.split("T")[0])

            target_date = today
            for i in range(30):
                if str(target_date) not in blocked_days:
                    break  
                target_date += timedelta(days=1)
            
            payload = {
                "date": str(target_date),
                "entryType": "dinner",
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
                                "message": f'"{recipe_name}" wurde erfolgreich für den {target_date.strftime("%d.%m.%Y")} eingetragen!'
                            }
                        )
                    except Exception as notify_err:
                        _LOGGER.error("Konnte Push-Nachricht nicht senden: %s", notify_err)

                    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
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
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

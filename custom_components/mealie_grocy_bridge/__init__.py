"""The Mealie Grocy Bridge integration."""
import logging
import aiohttp
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_TODO_ENTITY,  # NEU: Importiere den Key für die konfigurierte To-Do-Liste
)

_LOGGER = logging.getLogger(__name__)
CONF_EXCLUDED_FOODS = "excluded_foods"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mealie Grocy Bridge from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    config = {**entry.data, **entry.options}
    exclusions_raw = config.get(CONF_EXCLUDED_FOODS, "")
    excluded_foods_list = [item.strip() for item in exclusions_raw.split(",") if item.strip()]

    hass.data[DOMAIN][entry.entry_id] = {
        **config,
        "excluded_foods_list": excluded_foods_list
    }

    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Helper: Holt Rezepte sicher aus dem Daten-Coordinator
    def get_recipe_by_index(index: int):
        coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
        if not coordinator or not coordinator.data:
            _LOGGER.warning("Coordinator noch nicht bereit oder keine Rezepte geladen.")
            return None
        try:
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

        # Aktuelle Konfiguration laden und die ausgewählte To-Do-Liste auslesen
        current_config = hass.data[DOMAIN][entry.entry_id]
        todo_entity = current_config.get(CONF_TODO_ENTITY)

        # Fallback: Falls der Nutzer in den Optionen noch keine Liste gewählt hat
        if not todo_entity:
            _LOGGER.warning("Keine To-Do-Liste in den Integrations-Optionen ausgewählt! Nutze Standardliste 'todo.stuttgart'.")
            todo_entity = "todo.stuttgart"

        _LOGGER.info("Füge fehlende Zutaten für '%s' zur To-Do-Liste '%s' hinzu: %s", recipe.get("recipeName"), todo_entity, missing_ingredients)

        added_count = 0  # Zähler für erfolgreiche Zutaten

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
                added_count += 1  # Erfolgreich hinzugefügt -> hochzählen
            except Exception as err:
                _LOGGER.error("Fehler beim Hinzufügen von '%s' zur To-Do-Liste '%s': %s", ingredient, todo_entity, err)

        # NEU: Native Push-Benachrichtigung absetzen (nur wenn mindestens eine Zutat hinzugefügt wurde)
        if added_count > 0:
            try:
                # Schönen lesbaren Namen für die Liste extrahieren (z.B. "stuttgart" statt "todo.stuttgart")
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
            # 1. Freie Tage ermitteln
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
            
            # 2. POST an Mealie absetzen
            payload = {
                "date": str(target_date),
                "entryType": "dinner",
                "recipeId": recipe_id
            }
            
            post_url = f"{mealie_url}/api/households/mealplans"
            async with session.post(post_url, headers=mealie_headers, json=payload, timeout=10) as post_resp:
                if post_resp.status in [200, 201]:
                    _LOGGER.info("Erfolgreich '%s' bei Mealie für den %s geplant", recipe_name, target_date)
                    
                    # 3. Native Push-Benachrichtigung absetzen
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

                    # 4. Sensor SOFORT aktualisieren
                    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
                    if coordinator:
                        _LOGGER.info("Triggere sofortigen Sensor-Refresh...")
                        hass.async_create_task(coordinator.async_refresh())
                else:
                    error_text = await post_resp.text()
                    _LOGGER.error("Mealie API verweigerte das Eintragen: %s", error_text)

        except Exception as err:
            _LOGGER.error("Fehler bei der Kommunikation mit der Mealie-Speiseplan-API: %s", err)

    # Dienste im HA Core registrieren
    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)
    hass.services.async_register(DOMAIN, "set_to_next_free_day", handle_set_to_next_free_day)

    # Lade die Sensor-Plattform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird aufgerufen, wenn die Optionen in der UI geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

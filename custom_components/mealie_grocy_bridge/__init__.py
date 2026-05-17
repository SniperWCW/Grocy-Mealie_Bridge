"""The Mealie Grocy Bridge integration.

Diese Datei initialisiert die Integration, verarbeitet die Konfiguration aus der UI
und stellt die beiden zentralen Home Assistant Dienste (Services) bereit.
"""
import logging
import aiohttp
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Importe der Konstanten aus der lokalen const.py
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_TODO_ENTITY,  # Enthält die Entity-ID der in der UI gewählten To-Do-Liste
)

# Logger-Instanz für Fehlermeldungen und Status-Infos im Home Assistant Log
_LOGGER = logging.getLogger(__name__)
CONF_EXCLUDED_FOODS = "excluded_foods"

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

    # Registriert einen Listener, der feuert, wenn der Nutzer die Optionen in der UI speichert
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # -----------------------------------------------------------------
    # HELPER: Holt Rezepte sicher aus dem Daten-Coordinator
    # -----------------------------------------------------------------
    def get_recipe_by_index(index: int):
        """Hilfsfunktion, um anhand eines numerischen Index (z.B.

        aus dem Dashboard) das passende Rezept aus dem Speicher des
        Coordinators zu ziehen.
        """
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
        # 1. Rezept über den übergebenen Dienst-Index ermitteln
        recipe_index = int(call.data.get("recipe_index", 0))
        recipe = get_recipe_by_index(recipe_index)
        
        if not recipe:
            _LOGGER.error("Zutaten-Export fehlgeschlagen: Kein Rezept unter Index %s gefunden", recipe_index)
            return

        # 2. Prüfen, ob überhaupt Zutaten im Grocy-Bestand fehlen
        missing_ingredients = recipe.get("missingIngredients", [])
        if not missing_ingredients:
            _LOGGER.info("Keine fehlenden Zutaten für '%s' vorhanden.", recipe.get("recipeName"))
            return

        # 3. Ziel-To-Do-Liste aus der aktuellen Konfiguration bestimmen
        current_config = hass.data[DOMAIN][entry.entry_id]
        todo_entity = current_config.get(CONF_TODO_ENTITY)

        # Fallback-Sicherheit, falls in den Integrations-Optionen noch gähnende Leere herrscht
        if not todo_entity:
            _LOGGER.warning("Keine To-Do-Liste in den Integrations-Optionen ausgewählt! Nutze Standardliste 'todo.stuttgart'.")
            todo_entity = "todo.stuttgart"

        _LOGGER.info("Füge fehlende Zutaten für '%s' zur To-Do-Liste '%s' hinzu: %s", recipe.get("recipeName"), todo_entity, missing_ingredients)

        added_count = 0  # Lokaler Zähler für die Push-Nachricht am Ende

        # 4. Schleife über alle fehlenden Zutaten und Übergabe an HA To-Do-Dienst
        for ingredient in missing_ingredients:
            if not ingredient:
                continue
            try:
                # HA-interner Dienstaufruf: Erstellt eine Aufgabe auf der To-Do-Liste
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {
                        "entity_id": todo_entity,
                        "item": str(ingredient),
                        "description": f"für {recipe.get('recipeName')}" # Notiz, für welches Rezept das gedacht war
                    },
                    blocking=True # Wartet, bis der Eintrag geschrieben wurde (wichtig für den Zähler)
                )
                added_count += 1  
            except Exception as err:
                _LOGGER.error("Fehler beim Hinzufügen von '%s' zur To-Do-Liste '%s': %s", ingredient, todo_entity, err)

        # 5. Native Push-Benachrichtigung an alle verbundenen HA-Geräte absetzen
        if added_count > 0:
            try:
                # Formatiert "todo.einkauf_woche" sauber zu "Einkauf Woche" für die Nachricht
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
        # 1. Rezeptdaten anhand des Indexes laden
        recipe_index = int(call.data.get("recipe_index", 0))
        recipe = get_recipe_by_index(recipe_index)
        
        if not recipe:
            _LOGGER.error("Planung fehlgeschlagen: Kein Rezept unter Index %s gefunden", recipe_index)
            return

        recipe_id = recipe.get("recipeId")
        recipe_name = recipe.get("recipeName", "Unbekanntes Rezept")

        # 2. API-Verbindungsdaten für Mealie vorbereiten und URL-Formatierung absichern
        current_config = hass.data[DOMAIN][entry.entry_id]
        mealie_url = current_config[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"
            
        mealie_token = current_config[CONF_MEALIE_TOKEN]
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}
        
        # Holt die von HA gemanagte, asynchrone HTTP-Sitzung (verhindert Session-Leaks)
        session = async_get_clientsession(hass)

        # 3. Zeitfenster definieren (Ab heute für die nächsten 30 Tage)
        today = datetime.now().date()
        end_date = today + timedelta(days=30)
        plan_url = f"{mealie_url}/api/households/mealplans?startTime={today}&endTime={end_date}&perPage=-1"
        
        try:
            # --- SCHRITT A: Bestehenden Mealie-Speiseplan abrufen, um belegte Tage zu finden ---
            async with session.get(plan_url, headers=mealie_headers, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.error("Konnte Speiseplan von Mealie nicht abrufen. Status: %s", resp.status)
                    return
                
                mealplans = await resp.json()
                items = mealplans.get("items", mealplans) if isinstance(mealplans, dict) else mealplans
                
                # Set für blockierte Tage (Sets erlauben blitzschnelle 'in'-Abfragen)
                blocked_days = set()
                for plan in items:
                    # Wir prüfen nur Hauptgerichte ("dinner"). Frühstück/Lunch blockieren den Tag nicht.
                    if plan.get("entryType") == "dinner":
                        plan_date = plan.get("date")
                        if plan_date:
                            # Das ISO-Datum von Mealie ("2026-05-17T00:00:00") am 'T' trennen -> "2026-05-17"
                            blocked_days.add(plan_date.split("T")[0])

            # --- SCHRITT B: Den nächsten freien Tag ermitteln ---
            target_date = today
            for i in range(30):
                if str(target_date) not in blocked_days:
                    break  # Tag ist frei! Schleife abbrechen.
                target_date += timedelta(days=1) # Tag besetzt -> einen Tag weitergehen
            
            # --- SCHRITT C: POST-Request an Mealie senden, um das Rezept einzubuchen ---
            payload = {
                "date": str(target_date),
                "entryType": "dinner",
                "recipeId": recipe_id
            }
            
            post_url = f"{mealie_url}/api/households/mealplans"
            async with session.post(post_url, headers=mealie_headers, json=payload, timeout=10) as post_resp:
                if post_resp.status in [200, 201]:
                    _LOGGER.info("Erfolgreich '%s' bei Mealie für den %s geplant", recipe_name, target_date)
                    
                    # --- SCHRITT D: Push-Benachrichtigung über erfolgreiche Planung absetzen ---
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

                    # --- SCHRITT E: Sofort-Update des HA-Sensors erzwingen ---
                    # Da sich der Speiseplan geändert hat, muss der Sensor neu berechnen,
                    # sonst würde das gerade geplante Rezept fälschlicherweise noch 30 Min. in den Vorschlägen stehen.
                    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
                    if coordinator:
                        _LOGGER.info("Triggere sofortigen Sensor-Refresh...")
                        hass.async_create_task(coordinator.async_refresh())
                else:
                    error_text = await post_resp.text()
                    _LOGGER.error("Mealie API verweigerte das Eintragen: %s", error_text)

        except Exception as err:
            _LOGGER.error("Fehler bei der Kommunikation mit der Mealie-Speiseplan-API: %s", err)

    # -----------------------------------------------------------------
    # REGISTRIERUNG: Die Dienste im Home Assistant Core anmelden
    # -----------------------------------------------------------------
    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)
    hass.services.async_register(DOMAIN, "set_to_next_free_day", handle_set_to_next_free_day)

    # Reicht die Konfiguration an die sensor.py weiter, um die Sensor-Entitäten zu erstellen
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird aufgerufen, wenn der Nutzer die Integrationsoptionen in der HA-UI ändert.

    Triggert einen kompletten Reload der Integration, damit Änderungen (z.B.
    geänderte To-Do-Liste) sofort aktiv werden.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration gelöscht oder deaktiviert wird.

    Sorgt für ein sauberes Aufräumen im System.
    """
    # Entfernt die Sensor-Plattformen
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        # Löscht die im Speicher abgelegten Konfigurationsdaten der Instanz
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

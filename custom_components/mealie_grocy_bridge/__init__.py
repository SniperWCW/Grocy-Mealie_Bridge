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
)

_LOGGER = logging.getLogger(__name__)
CONF_EXCLUDED_FOODS = "excluded_foods"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mealie Grocy Bridge from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Führe data und options zusammen (Optionen überschreiben die Ersteinrichtung)
    config = {**entry.data, **entry.options}
    
    # Wandle den kommagetrennten String der Ausschlüsse in eine saubere Python-Liste um
    exclusions_raw = config.get(CONF_EXCLUDED_FOODS, "")
    excluded_foods_list = [item.strip() for item in exclusions_raw.split(",") if item.strip()]

    # Speichere die verarbeiteten Daten ab
    hass.data[DOMAIN][entry.entry_id] = {
        **config,
        "excluded_foods_list": excluded_foods_list
    }

    # Registriere den Listener, der bei Änderungen im "Konfigurieren"-Menü feuert
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # =====================================================================
    # DIENST 1: Fehlende Zutaten zur Bring-Liste (To-Do-Entität) hinzufügen
    # =====================================================================
    async def handle_add_missing_ingredients(call: ServiceCall):
        """Fügt die fehlenden Zutaten eines bestimmten Rezepts zu Bring hinzu."""
        missing_ingredients = call.data.get("ingredients", [])
        
        if isinstance(missing_ingredients, str):
            # Falls die Zutaten als kommagetrennter String kommen, in eine Liste wandeln
            missing_ingredients = [i.strip() for i in missing_ingredients.split(",")]

        _LOGGER.info("Füge fehlende Zutaten zu Bring hinzu: %s", missing_ingredients)

        for ingredient in missing_ingredients:
            if not ingredient:
                continue
                
            try:
                # Direktes Hinzufügen zur Bring-To-Do-Liste in Home Assistant
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {
                        "entity_id": "todo.stuttgart",
                        "item": ingredient,
                        "description": "Aus Mealie Rezeptvorschlag"
                    },
                    blocking=True
                )
            except Exception as err:
                _LOGGER.error("Fehler beim Hinzufügen von '%s' zu Bring: %s", ingredient, err)

    # Registriere den Bring-Dienst im System
    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)


    # =====================================================================
    # DIENST 2: Rezept auf den nächsten freien Tag im Mealie-Speiseplan setzen
    # =====================================================================
    async def handle_set_to_next_free_day(call: ServiceCall):
        """Findet den nächsten freien Tag bei Mealie und trägt das gewählte Rezept ein."""
        recipe_id = call.data.get("recipe_id")
        if not recipe_id:
            _LOGGER.error("Dienst 'set_to_next_free_day' wurde ohne recipe_id aufgerufen")
            return

        # Hol die aktuellen Verbindungsdaten aus hass.data
        current_config = hass.data[DOMAIN][entry.entry_id]
        
        mealie_url = current_config[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"
            
        mealie_token = current_config[CONF_MEALIE_TOKEN]
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}
        
        # Nutzt die bestehende aiohttp-Session von Home Assistant
        session = async_get_clientsession(hass)

        # Zeitfenster für die Suche nach freien Tagen generieren (30 Tage ab heute)
        today = datetime.now().date()
        end_date = today + timedelta(days=30)
        
        # JETZT NEU: Der korrekte Pfad laut deiner Swagger-Doku
        plan_url = f"{mealie_url}/api/households/mealplans?startTime={today}&endTime={end_date}&perPage=-1"
        
        try:
            # 1. Den aktuellen Speiseplan der nächsten 30 Tage abrufen
            async with session.get(plan_url, headers=mealie_headers, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.error("Konnte Speiseplan von Mealie nicht abrufen. Status: %s", resp.status)
                    return
                
                mealplans = await resp.json()
                items = mealplans.get("items", mealplans) if isinstance(mealplans, dict) else mealplans
                
                # Wir sammeln alle Tage, an denen beim Abendessen ('dinner') schon etwas eingetragen ist
                blocked_days = set()
                for plan in items:
                    if plan.get("entryType") == "dinner":
                        plan_date = plan.get("date")
                        if plan_date:
                            blocked_days.add(plan_date.split("T")[0])

            # 2. Den ersten freien Tag ab heute ermitteln
            target_date = today
            for i in range(30):
                if str(target_date) not in blocked_days:
                    break  # Tag ist frei, Schleife abbrechen!
                target_date += timedelta(days=1)
            
            _LOGGER.info("Nächster freier Speiseplan-Tag ermittelt: %s. Trage Rezept-ID %s ein.", target_date, recipe_id)
            
            # 3. Das Gericht bei Mealie für diesen Tag als Abendessen eintragen
            payload = {
                "date": str(target_date),
                "entryType": "dinner",
                "recipeId": recipe_id
            }
            
            # JETZT NEU: Der korrekte POST-Pfad laut deiner Swagger-Doku
            post_url = f"{mealie_url}/api/households/mealplans"
            async with session.post(post_url, headers=mealie_headers, json=payload, timeout=10) as post_resp:
                if post_resp.status in [200, 201]:
                    _LOGGER.info("Erfolgreich Rezept %s bei Mealie für den %s geplant", recipe_id, target_date)
                    
                    # 4. Sofortiges Update des Sensor-Coordinators triggern, damit das Rezept direkt verschwindet
                    # Wir suchen uns die geladene Instanz des Coordinators aus hass.data (falls vorhanden)
                    if "sensor" in hass.data[DOMAIN]:
                        # Ein erzwungener Refresh aktualisiert den Sensor sofort ohne die 30 Minuten abzuwarten
                        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
                else:
                    error_text = await post_resp.text()
                    _LOGGER.error("Mealie API verweigerte das Eintragen des Speiseplans: %s", error_text)

        except Exception as err:
            _LOGGER.error("Fehler bei der Kommunikation mit der Mealie-Speiseplan-API: %s", err)

    # Registriere den neuen Speiseplan-Dienst im System
    hass.services.async_register(DOMAIN, "set_to_next_free_day", handle_set_to_next_free_day)


    # Lade die Sensor-Plattform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird aufgerufen, wenn die Optionen in der UI geändert wurden."""
    _LOGGER.info("Konfiguration der Mealie Grocy Bridge wurde aktualisiert. Lade neu...")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

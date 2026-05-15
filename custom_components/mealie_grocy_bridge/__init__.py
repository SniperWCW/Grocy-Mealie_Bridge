"""The Mealie Grocy Bridge integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN

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

    # Registriere die Aktion für das rezeptgenaue Hinzufügen von Zutaten
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

    # Registriere den neuen Dienst im System
    hass.services.async_register(DOMAIN, "add_missing_ingredients", handle_add_missing_ingredients)

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

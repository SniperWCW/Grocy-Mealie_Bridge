"""The Mealie Grocy Bridge integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mealie Grocy Bridge from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

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

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

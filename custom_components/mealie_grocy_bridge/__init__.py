"""The Mealie Grocy Bridge integration."""
import logging
import asyncio
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mealie Grocy Bridge from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Registriere die Aktion für die Synchronisation
    async def handle_sync_shopping_list(call: ServiceCall):
        """Gleicht die Grocy Einkaufsliste mit der Bring To-Do Liste ab."""
        config = entry.data
        grocy_url = config[CONF_GROCY_URL].rstrip("/")
        if not grocy_url.startswith(("http://", "https://")):
            grocy_url = f"http://{grocy_url}"
        grocy_token = config[CONF_GROCY_TOKEN]

        session = async_get_clientsession(hass)
        grocy_headers = {"GROCY-API-KEY": grocy_token}

        _LOGGER.info("Starte Mealie-Grocy Einkaufslisten-Synchronisation...")

        try:
            # 1. Grocy Einkaufsliste abrufen
            async with session.get(f"{grocy_url}/api/objects/shopping_list", headers=grocy_headers, timeout=10) as res:
                if res.status != 200:
                    _LOGGER.error("Grocy Shopping List API Fehler: %s", res.status)
                    return
                grocy_list = await res.json()

            # 2. Grocy Artikel-Stammdaten abrufen (für die Klarnamen)
            async with session.get(f"{grocy_url}/api/objects/products", headers=headers=grocy_headers, timeout=10) as res:
                if res.status != 200:
                    _LOGGER.error("Grocy Products API Fehler: %s", res.status)
                    return
                grocy_products = await res.json()

            # Mapping erstellen für ID -> Produktname
            product_map = {str(p["id"]): p["name"] for p in grocy_products if "id" in p and "name" in p}

            # 3. Bring-Liste aus Home Assistant abrufen (todo.stuttgart)
            # Wir nutzen den nativen HA-Dienst, genau wie im n8n Flow
            try:
                todo_response = await hass.services.async_call(
                    "todo",
                    "get_items",
                    {"entity_id": "todo.stuttgart", "status": "needs_action"},
                    blocking=True,
                    return_response=True
                )
                bring_items = todo_response.get("todo.stuttgart", {}).get("items", [])
            except Exception as todo_err:
                _LOGGER.error("Fehler beim Abrufen der HA To-Do Liste: %s", todo_err)
                return

            # Bestehende Bring-Einträge für den Abgleich vorbereiten (kleingeschrieben)
            bring_names = [str(b["summary"]).lower().strip() for b in bring_items if "summary" in b]

            # 4. Daten abgleichen und fehlende Artikel hinzufügen
            for item in grocy_list:
                p_id = str(item.get("product_id"))
                grocy_id = item.get("id")
                amount = int(float(item.get("amount", 1)))

                if p_id in product_map:
                    product_name = product_map[p_id]
                    product_name_low = product_name.lower().strip()

                    # Wenn der Artikel noch NICHT auf der Bring-Liste steht:
                    if product_name_low not in bring_names:
                        _LOGGER.info("Füge hinzu zu Bring: %s (%sx)", product_name, amount)
                        
                        # Artikel zu Bring hinzufügen
                        await hass.services.async_call(
                            "todo",
                            "add_item",
                            {
                                "entity_id": "todo.stuttgart",
                                "item": product_name,
                                "description": f"{amount}x für Grocy"
                            },
                            blocking=True
                        )

                        # Artikel aus der Grocy-Einkaufsliste löschen, da er jetzt im Bring ist
                        try:
                            async with session.delete(f"{grocy_url}/api/objects/shopping_list/{grocy_id}", headers=grocy_headers, timeout=5) as del_res:
                                if del_res.status in [200, 204]:
                                    _LOGGER.info("Aus Grocy-Liste gelöscht: %s", product_name)
                                else:
                                    _LOGGER.warning("Konnte Artikel %s nicht aus Grocy löschen: %s", product_name, del_res.status)
                        except Exception as del_err:
                            _LOGGER.error("Fehler beim Löschen aus Grocy: %s", del_err)

        except Exception as err:
            _LOGGER.error("Unerwarteter Fehler bei der Listen-Synchronisation: %s", err)

    # Registriere die Aktion im System
    hass.services.async_register(DOMAIN, "sync_shopping_list", handle_sync_shopping_list)

    # Lade die Plattformen (Sensor) wie gehabt
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

"""Transfer the Grocy shopping list to a Home Assistant to-do list.

Replaces the former n8n flow "Grocy → HA Einkaufsliste": every open entry of
the Grocy shopping list is added to the configured to-do list (for example
the Bring list) and then removed from Grocy (or marked as done there).
Entries that are already open on the to-do list are not added twice, but are
still removed from Grocy so they do not come back after being checked off.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    CONF_GROCY_SHOPPING_AFTER,
    CONF_GROCY_TOKEN,
    CONF_GROCY_URL,
    CONF_TODO_ENTITY,
    DOMAIN,
    GROCY_SHOPPING_AFTER_DELETE,
    REQUEST_TIMEOUT,
    normalize_base_url,
)
from .shopping_plan import plan_transfer

_LOGGER = logging.getLogger(__name__)

EVENT_SHOPPING_SYNCED = f"{DOMAIN}_shopping_list_synced"


async def _grocy_get(session, url, headers):
    async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"{url.rsplit('/api/', 1)[-1]}: HTTP {response.status}")
        return await response.json()


async def async_sync_shopping_list(hass: HomeAssistant, runtime_data: dict) -> dict:
    """Run one transfer from Grocy to the to-do list and return a summary."""
    lock: asyncio.Lock = runtime_data.setdefault("shopping_sync_lock", asyncio.Lock())
    if lock.locked():
        return {"status": "busy", "transferred": [], "already_on_list": [], "errors": []}

    async with lock:
        result = await _async_run_sync(hass, runtime_data)

    runtime_data["last_shopping_sync"] = result
    hass.bus.async_fire(EVENT_SHOPPING_SYNCED, result)
    if result["errors"]:
        _LOGGER.warning("Grocy-Einkaufslisten-Sync mit Fehlern: %s", "; ".join(result["errors"]))
    elif result["transferred"] or result["already_on_list"]:
        _LOGGER.info(
            "Grocy-Einkaufslisten-Sync: %s übertragen, %s standen schon auf der Liste",
            len(result["transferred"]),
            len(result["already_on_list"]),
        )
    return result


async def _async_run_sync(hass: HomeAssistant, runtime_data: dict) -> dict:
    """Do the actual transfer (called with the lock held)."""
    result = {
        "status": "ok",
        "time": dt_util.now().isoformat(),
        "transferred": [],
        "already_on_list": [],
        "errors": [],
    }
    todo_entity = runtime_data.get(CONF_TODO_ENTITY)
    if not todo_entity:
        result["status"] = "error"
        result["errors"].append("Keine To-do-Liste in der Bridge konfiguriert")
        return result

    delete_after = (
        runtime_data.get(CONF_GROCY_SHOPPING_AFTER, GROCY_SHOPPING_AFTER_DELETE)
        == GROCY_SHOPPING_AFTER_DELETE
    )
    grocy_url = normalize_base_url(runtime_data[CONF_GROCY_URL])
    headers = {"GROCY-API-KEY": runtime_data[CONF_GROCY_TOKEN]}
    session = async_get_clientsession(hass)

    try:
        shopping_items, products, quantity_units = await asyncio.gather(
            _grocy_get(session, f"{grocy_url}/api/objects/shopping_list", headers),
            _grocy_get(session, f"{grocy_url}/api/objects/products", headers),
            _grocy_get(session, f"{grocy_url}/api/objects/quantity_units", headers),
        )
    except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
        result["status"] = "error"
        result["errors"].append(f"Grocy nicht abrufbar: {err}")
        return result

    if not shopping_items:
        return result

    # Imported here to avoid a circular import with __init__.py
    from . import _fetch_todo_items

    existing = [
        item.get("summary") or item.get("item") or ""
        for item in await _fetch_todo_items(hass, todo_entity)
        if isinstance(item, dict)
    ]
    plan = plan_transfer(shopping_items, products, quantity_units, existing)
    result["errors"].extend(plan.unresolved)

    for transfer in plan.transfers:
        if transfer.already_on_list:
            target = result["already_on_list"]
        else:
            try:
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {"entity_id": todo_entity, "item": transfer.name, "description": transfer.description},
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001
                result["errors"].append(f"{transfer.name}: Hinzufügen fehlgeschlagen ({err})")
                continue  # keep it in Grocy so the next run retries
            target = result["transferred"]

        entry_url = f"{grocy_url}/api/objects/shopping_list/{transfer.grocy_id}"
        try:
            if delete_after:
                request = session.delete(entry_url, headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                request = session.put(entry_url, headers=headers, json={"done": 1}, timeout=REQUEST_TIMEOUT)
            async with request as response:
                if response.status not in (200, 204):
                    result["errors"].append(
                        f"{transfer.name}: Grocy-Eintrag nicht entfernt (HTTP {response.status})"
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            result["errors"].append(f"{transfer.name}: Grocy-Eintrag nicht entfernt ({err})")
        target.append(transfer.name)

    if result["errors"]:
        result["status"] = "partial" if (result["transferred"] or result["already_on_list"]) else "error"
    return result

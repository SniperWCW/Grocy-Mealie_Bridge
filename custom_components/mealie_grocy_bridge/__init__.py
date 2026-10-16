"""The Mealie Grocy Bridge integration."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import aiohttp
import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import (
    CoreState,
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_MEALPLAN_SYNC_ENABLED,
    CONF_DAILY_MEALPLAN_SYNC_TIME,
    CONF_EXCLUDED_FOODS,
    CONF_GROCY_SHOPPING_SYNC_ENABLED,
    CONF_GROCY_SHOPPING_SYNC_INTERVAL,
    CONF_GROCY_TOKEN,
    CONF_GROCY_URL,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    CONF_MEALPLAN_SYNC_DAYS_AHEAD,
    CONF_MEALPLAN_SYNC_MODE,
    CONF_MEALPLAN_SYNC_WEEKDAY,
    CONF_OFF_SYNC_ENABLED,
    CONF_OFF_SYNC_TIME,
    CONF_OFF_SYNC_WEEKDAY,
    CONF_TODO_ENTITY,
    DEFAULT_GROCY_SHOPPING_SYNC_INTERVAL,
    DOMAIN,
    MEALPLAN_SYNC_MODE_WEEKLY,
    MEALPLAN_SYNC_MODE_DAILY,
    REQUEST_TIMEOUT,
    normalize_base_url,
    parse_mealplan_date,
)
from .matching import analyze_recipe, build_products_map, normalize_list_item
from .openfoodfacts import DEFAULT_LIMIT as OFF_DEFAULT_LIMIT, async_enrich_from_openfoodfacts
from .shopping_sync import async_sync_shopping_list

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]
URL_BASE = "/mealie_grocy_bridge_ui"
CARD_FILENAME = "mealie-grocy-card.js"
SYNCABLE_ENTRY_TYPES = {"lunch", "dinner"}
ENTRY_TYPES = ["breakfast", "lunch", "dinner", "side"]
WEEKDAY_NAME_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
DATA_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_RECIPE_TARGET = {
    vol.Optional("recipe_id"): cv.string,
    vol.Optional("recipe_index"): vol.All(vol.Coerce(int), vol.Range(min=0)),
}
ADD_MISSING_SCHEMA = vol.All(
    vol.Schema(_RECIPE_TARGET),
    cv.has_at_least_one_key("recipe_id", "recipe_index"),
)
SET_NEXT_FREE_DAY_SCHEMA = vol.All(
    vol.Schema(
        {
            **_RECIPE_TARGET,
            vol.Optional("selected_date"): vol.Any(None, "", cv.date),
            vol.Optional("entry_type", default="dinner"): vol.In(ENTRY_TYPES),
        }
    ),
    cv.has_at_least_one_key("recipe_id", "recipe_index"),
)
ENRICH_OFF_SCHEMA = vol.Schema(
    {
        vol.Optional("dry_run", default=True): cv.boolean,
        vol.Optional("limit", default=OFF_DEFAULT_LIMIT): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        vol.Optional("include_calories", default=True): cv.boolean,
        vol.Optional("include_images", default=True): cv.boolean,
        vol.Optional("exclude_product_groups", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("name_check", default=True): cv.boolean,
        vol.Optional("confirm_barcodes", default=[]): vol.All(cv.ensure_list, [cv.string]),
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_entry_runtime(hass: HomeAssistant, entry_id: str) -> dict:
    """Return the runtime data for a config entry."""
    return hass.data.get(DOMAIN, {}).get(entry_id, {})


def _get_active_runtime(hass: HomeAssistant) -> dict:
    """Return the runtime data of the loaded config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            runtime = _get_entry_runtime(hass, entry.entry_id)
            if runtime:
                return runtime
    raise ServiceValidationError("Mealie Grocy Bridge ist nicht geladen.")


def _coerce_time_value(value) -> tuple[int, int]:
    """Convert configured time values to hour and minute."""
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour), int(value.minute)
    parts = str(value or "07:00").strip().split(":")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return 7, 0


def _recipe_matches_mealplan_entry(recipe_details, recipe_id, recipe_slug) -> bool:
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
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Konnte bestehende To-Do-Eintraege fuer %s nicht laden: %s", todo_entity, err)
        return []
    if not isinstance(response, dict):
        return []
    entity_response = response.get(todo_entity, {})
    return entity_response.get("items", []) if isinstance(entity_response, dict) else []


async def _add_items_to_todo(
    hass: HomeAssistant, todo_entity: str, items: list[str], description: str
) -> int:
    """Add items to a to-do list, skipping ones that are already open."""
    existing = {
        normalize_list_item(item.get("summary") or item.get("item") or "")
        for item in await _fetch_todo_items(hass, todo_entity)
        if isinstance(item, dict)
    }
    added = 0
    for item in items:
        normalized = normalize_list_item(item)
        if not normalized or normalized in existing:
            continue
        try:
            await hass.services.async_call(
                "todo",
                "add_item",
                {"entity_id": todo_entity, "item": str(item), "description": description},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Fehler beim Hinzufuegen von '%s' zu %s: %s", item, todo_entity, err)
            continue
        existing.add(normalized)
        added += 1
    return added


async def _notify(hass: HomeAssistant, title: str, message: str) -> None:
    """Send a notification if a notify service is available."""
    if not hass.services.has_service("notify", "notify"):
        _LOGGER.debug("Kein notify.notify vorhanden, Benachrichtigung uebersprungen: %s", message)
        return
    try:
        await hass.services.async_call("notify", "notify", {"title": title, "message": message})
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Konnte Push-Nachricht nicht senden: %s", err)


def _resolve_sync_target_dates(runtime_data: dict, now_date: date) -> list[date]:
    """Resolve the meal plan dates for the current sync run."""
    if runtime_data.get(CONF_MEALPLAN_SYNC_MODE, MEALPLAN_SYNC_MODE_DAILY) != MEALPLAN_SYNC_MODE_WEEKLY:
        return [now_date]

    weekday = str(runtime_data.get(CONF_MEALPLAN_SYNC_WEEKDAY, "sunday")).strip().lower()
    if now_date.weekday() != WEEKDAY_NAME_TO_INDEX.get(weekday, 6):
        return []
    try:
        days_ahead = int(runtime_data.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7))
    except (TypeError, ValueError):
        days_ahead = 7
    days_ahead = max(1, min(days_ahead, 14))
    return [now_date + timedelta(days=offset) for offset in range(days_ahead)]


def _format_sync_range_label(target_dates: list[date]) -> str:
    """Build a human-readable label for sync logging and todo descriptions."""
    if not target_dates:
        return ""
    if len(target_dates) == 1:
        return target_dates[0].strftime("%d.%m.%Y")
    return f"{target_dates[0].strftime('%d.%m.%Y')} bis {target_dates[-1].strftime('%d.%m.%Y')}"


# ---------------------------------------------------------------------------
# Meal plan sync
# ---------------------------------------------------------------------------


async def _run_mealplan_sync(hass: HomeAssistant, entry_id: str, target_dates: list[date]) -> None:
    """Sync missing ingredients from the configured meal plan dates to the todo list."""
    runtime_data = _get_entry_runtime(hass, entry_id)
    if not runtime_data or not target_dates:
        return

    todo_entity = runtime_data.get(CONF_TODO_ENTITY)
    if not todo_entity:
        _LOGGER.warning("Essensplan-Sync uebersprungen: keine To-Do-Liste konfiguriert.")
        return

    mealie_url = normalize_base_url(runtime_data[CONF_MEALIE_URL])
    grocy_url = normalize_base_url(runtime_data[CONF_GROCY_URL])
    session = async_get_clientsession(hass)
    mealie_headers = {"Authorization": f"Bearer {runtime_data[CONF_MEALIE_TOKEN]}"}
    grocy_headers = {"GROCY-API-KEY": runtime_data[CONF_GROCY_TOKEN]}
    basics = runtime_data.get("excluded_foods_list", [])
    target_date_set = set(target_dates)
    sync_range_label = _format_sync_range_label(target_dates)

    mealplan_url = (
        f"{mealie_url}/api/households/mealplans"
        f"?startTime={min(target_date_set).isoformat()}"
        f"&endTime={max(target_date_set).isoformat()}&perPage=-1"
    )
    try:
        async with session.get(mealplan_url, headers=mealie_headers, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 200:
                _LOGGER.error("Essensplan-Sync: Mealie-Speiseplan konnte nicht geladen werden (%s).", response.status)
                return
            mealplan_data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.error("Essensplan-Sync: Fehler beim Abrufen des Speiseplans: %s", err)
        return

    items = mealplan_data.get("items", mealplan_data) if isinstance(mealplan_data, dict) else mealplan_data
    matching_plans = [
        plan
        for plan in (items or [])
        if isinstance(plan, dict)
        and str(plan.get("entryType", "")).strip().lower() in SYNCABLE_ENTRY_TYPES
        and parse_mealplan_date(plan) in target_date_set
    ]
    if not matching_plans:
        _LOGGER.info("Essensplan-Sync: kein Mittag- oder Abendessen fuer %s gefunden.", sync_range_label)
        return

    try:
        async with session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 200:
                _LOGGER.error("Essensplan-Sync: Grocy-Bestand konnte nicht geladen werden (%s).", response.status)
                return
            grocy_data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.error("Essensplan-Sync: Fehler beim Abrufen des Grocy-Bestands: %s", err)
        return

    products_map = build_products_map(grocy_data, dt_util.now().date())
    missing_ingredients: list[str] = []

    for plan in matching_plans:
        recipe_obj = plan.get("recipe") if isinstance(plan.get("recipe"), dict) else {}
        recipe_id = str(plan.get("recipeId") or recipe_obj.get("id") or "").strip() or None
        recipe_slug = str(recipe_obj.get("slug") or "").strip() or None
        recipe_name = recipe_obj.get("name") or plan.get("title") or plan.get("text") or "Unbekanntes Rezept"
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
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Essensplan-Sync: Rezept %s konnte nicht geladen werden (%s).",
                        recipe_identifier,
                        response.status,
                    )
                    continue
                recipe_details = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
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

        missing_ingredients.extend(analyze_recipe(recipe_details, products_map, basics)["missingIngredients"])

    if not missing_ingredients:
        _LOGGER.info("Essensplan-Sync: keine fehlenden Zutaten fuer %s gefunden.", sync_range_label)
        return

    added_count = await _add_items_to_todo(
        hass, todo_entity, missing_ingredients, f"fuer Essensplan {sync_range_label}"
    )
    _LOGGER.info(
        "Essensplan-Sync abgeschlossen: %s neue Eintraege fuer %s zur Liste %s hinzugefuegt.",
        added_count,
        sync_range_label,
        todo_entity,
    )


def _setup_daily_mealplan_sync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the meal plan sync based on the current config."""
    runtime_data = _get_entry_runtime(hass, entry.entry_id)
    if not runtime_data or not runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED):
        return

    hour, minute = _coerce_time_value(runtime_data.get(CONF_DAILY_MEALPLAN_SYNC_TIME, "07:00"))

    async def _handle_daily_sync(_now) -> None:
        target_dates = _resolve_sync_target_dates(runtime_data, dt_util.now().date())
        if target_dates:
            await _run_mealplan_sync(hass, entry.entry_id, target_dates)

    entry.async_on_unload(
        async_track_time_change(hass, _handle_daily_sync, hour=hour, minute=minute, second=0)
    )


def _setup_grocy_shopping_sync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Poll the Grocy shopping list and transfer it to the to-do list."""
    runtime_data = _get_entry_runtime(hass, entry.entry_id)
    if not runtime_data or not runtime_data.get(CONF_GROCY_SHOPPING_SYNC_ENABLED):
        return

    try:
        minutes = int(runtime_data.get(CONF_GROCY_SHOPPING_SYNC_INTERVAL, DEFAULT_GROCY_SHOPPING_SYNC_INTERVAL))
    except (TypeError, ValueError):
        minutes = DEFAULT_GROCY_SHOPPING_SYNC_INTERVAL
    minutes = max(1, min(minutes, 1440))

    async def _handle_interval(_now) -> None:
        await async_sync_shopping_list(hass, runtime_data)

    entry.async_on_unload(
        async_track_time_interval(hass, _handle_interval, timedelta(minutes=minutes))
    )

    if hass.state is CoreState.running:
        entry.async_create_background_task(
            hass, async_sync_shopping_list(hass, runtime_data), "grocy_shopping_initial_sync"
        )
        return

    unsub_started = None

    async def _initial_sync(_event: Event) -> None:
        nonlocal unsub_started
        unsub_started = None
        await async_sync_shopping_list(hass, runtime_data)

    def _cancel_initial_sync() -> None:
        if unsub_started:
            unsub_started()

    unsub_started = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _initial_sync)
    entry.async_on_unload(_cancel_initial_sync)


OFF_SCHEDULED_LIMIT = 50


def _setup_openfoodfacts_sync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Fill missing calories and pictures from Open Food Facts once a week."""
    runtime_data = _get_entry_runtime(hass, entry.entry_id)
    if not runtime_data or not runtime_data.get(CONF_OFF_SYNC_ENABLED):
        return

    hour, minute = _coerce_time_value(runtime_data.get(CONF_OFF_SYNC_TIME, "03:30"))
    weekday = str(runtime_data.get(CONF_OFF_SYNC_WEEKDAY, "sunday")).strip().lower()
    weekday_index = WEEKDAY_NAME_TO_INDEX.get(weekday, 6)

    async def _handle_weekly(_now) -> None:
        if dt_util.now().weekday() != weekday_index:
            return
        result = await async_enrich_from_openfoodfacts(
            hass, runtime_data, dry_run=False, limit=OFF_SCHEDULED_LIMIT
        )
        # Only tell about news: written products and mismatches not reported before.
        reported: set = runtime_data.setdefault("off_reported_mismatch", set())
        new_mismatch = [e for e in result.get("name_mismatch", []) if e.get("barcode") not in reported]
        reported.update(e.get("barcode") for e in result.get("name_mismatch", []))
        lines = []
        if result.get("updates"):
            lines.append(f"{len(result['updates'])} Produkte in Grocy ergänzt.")
        if new_mismatch:
            names = ", ".join(f"{e['name']} ({e['barcode']})" for e in new_mismatch[:5])
            lines.append(f"Name prüfen, nicht geschrieben: {names}.")
        if result.get("errors"):
            lines.append(f"{len(result['errors'])} Fehler, Details im Log.")
        if lines:
            await _notify(hass, "Open Food Facts", " ".join(lines))

    entry.async_on_unload(
        async_track_time_change(hass, _handle_weekly, hour=hour, minute=minute, second=0)
    )


def _prepare_runtime_config(config: dict) -> dict:
    """Normalize UI config into runtime-friendly values."""
    exclusions_raw = config.get(CONF_EXCLUDED_FOODS, "") or ""
    excluded_foods_list = [item.strip().lower() for item in exclusions_raw.split(",") if item.strip()]
    try:
        config[CONF_MEALPLAN_SYNC_DAYS_AHEAD] = int(config.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7))
    except (TypeError, ValueError):
        config[CONF_MEALPLAN_SYNC_DAYS_AHEAD] = 7
    return {**config, "excluded_foods_list": excluded_foods_list}


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the custom card and register it as a Lovelace resource."""
    if hass.data.get(DATA_FRONTEND_REGISTERED):
        return
    hass.data[DATA_FRONTEND_REGISTERED] = True

    integration = await async_get_integration(hass, DOMAIN)
    frontend_dir = str(integration.file_path / "frontend")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, frontend_dir, cache_headers=False)]
    )

    card_url_base = f"{URL_BASE}/{CARD_FILENAME}"
    card_url = f"{card_url_base}?v={integration.version or 'dev'}"

    async def _register_resource(_event: Event | None = None) -> None:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None or not hasattr(resources, "async_create_item"):
            _LOGGER.info(
                "Lovelace-Ressourcen werden per YAML verwaltet. Bitte %s manuell als Modul eintragen.",
                card_url,
            )
            return
        try:
            # Ensures the storage collection is loaded before reading it.
            await resources.async_get_info()
            matching = [
                item
                for item in resources.async_items()
                if str(item.get("url") or "").split("?", 1)[0] == card_url_base
            ]
            if any(item.get("url") == card_url for item in matching):
                keep_id = next(item["id"] for item in matching if item.get("url") == card_url)
            elif matching:
                keep_id = matching[0]["id"]
                await resources.async_update_item(keep_id, {"res_type": "module", "url": card_url})
            else:
                keep_id = (await resources.async_create_item({"res_type": "module", "url": card_url}))["id"]
            for item in matching:
                if item["id"] != keep_id:
                    await resources.async_delete_item(item["id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Fehler bei der Registrierung der Lovelace-Ressource: %s", err)

    if hass.state is CoreState.running:
        await _register_resource()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_resource)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _get_recipe(runtime_data: dict, call: ServiceCall) -> dict:
    """Return a recipe from the coordinator by id (preferred) or index."""
    coordinator = runtime_data.get("coordinator")
    recipes = (coordinator.data if coordinator else None) or []
    recipe_id = str(call.data.get("recipe_id") or "").strip()

    if recipe_id:
        for recipe in recipes:
            if str(recipe.get("recipeId")) == recipe_id:
                return recipe
        raise ServiceValidationError(f"Rezept mit ID {recipe_id} ist nicht in den Kochvorschlaegen.")

    index = call.data.get("recipe_index", 0)
    if 0 <= index < len(recipes):
        return recipes[index]
    raise ServiceValidationError(f"Kein Rezept unter Index {index} gefunden.")


async def _handle_add_missing_ingredients(hass: HomeAssistant, call: ServiceCall) -> None:
    """Add missing ingredients of one recipe to the configured to-do list."""
    runtime_data = _get_active_runtime(hass)
    recipe = _get_recipe(runtime_data, call)
    todo_entity = runtime_data.get(CONF_TODO_ENTITY)
    if not todo_entity:
        raise ServiceValidationError("Keine To-do-Liste in der Bridge konfiguriert.")

    missing = [str(item) for item in recipe.get("missingIngredients", []) if item]
    if not missing:
        _LOGGER.info("Keine fehlenden Zutaten fuer '%s' vorhanden.", recipe.get("recipeName"))
        return

    added_count = await _add_items_to_todo(hass, todo_entity, missing, f"fuer {recipe.get('recipeName')}")
    if added_count:
        list_name = todo_entity.split(".")[-1].replace("_", " ").title()
        await _notify(
            hass,
            "Einkaufsliste aktualisiert",
            f"{added_count} fehlende Zutat(en) fuer '{recipe.get('recipeName')}' "
            f"wurden zur Liste '{list_name}' hinzugefuegt.",
        )


async def _handle_set_to_next_free_day(hass: HomeAssistant, call: ServiceCall) -> None:
    """Schedule the recipe on the selected date or the next free day."""
    runtime_data = _get_active_runtime(hass)
    recipe = _get_recipe(runtime_data, call)
    recipe_id = recipe.get("recipeId")
    recipe_name = recipe.get("recipeName", "Unbekanntes Rezept")
    entry_type = call.data.get("entry_type", "dinner")

    mealie_url = normalize_base_url(runtime_data[CONF_MEALIE_URL])
    mealie_headers = {"Authorization": f"Bearer {runtime_data[CONF_MEALIE_TOKEN]}"}
    session = async_get_clientsession(hass)

    selected_date = call.data.get("selected_date")
    if selected_date:
        target_date = selected_date
    else:
        today = dt_util.now().date()
        plan_url = (
            f"{mealie_url}/api/households/mealplans"
            f"?startTime={today}&endTime={today + timedelta(days=30)}&perPage=-1"
        )
        try:
            async with session.get(plan_url, headers=mealie_headers, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    raise ServiceValidationError(f"Mealie-Speiseplan nicht abrufbar (HTTP {resp.status}).")
                mealplans = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ServiceValidationError(f"Mealie nicht erreichbar: {err}") from err

        items = mealplans.get("items", mealplans) if isinstance(mealplans, dict) else mealplans
        blocked_days = {
            parse_mealplan_date(plan)
            for plan in items or []
            if isinstance(plan, dict) and str(plan.get("entryType", "")).strip().lower() == entry_type
        }
        target_date = today
        for _ in range(30):
            if target_date not in blocked_days:
                break
            target_date += timedelta(days=1)

    payload = {"date": target_date.isoformat(), "entryType": entry_type, "recipeId": recipe_id}
    try:
        async with session.post(
            f"{mealie_url}/api/households/mealplans",
            headers=mealie_headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        ) as post_resp:
            if post_resp.status not in (200, 201):
                raise ServiceValidationError(f"Mealie verweigerte das Eintragen: {await post_resp.text()}")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ServiceValidationError(f"Mealie nicht erreichbar: {err}") from err

    await _notify(
        hass,
        "Mealie Speiseplan",
        f'"{recipe_name}" wurde fuer den {target_date.strftime("%d.%m.%Y")} als {entry_type} eingetragen.',
    )
    coordinator = runtime_data.get("coordinator")
    if coordinator:
        await coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services once."""

    async def add_missing(call: ServiceCall) -> None:
        await _handle_add_missing_ingredients(hass, call)

    async def set_next_free_day(call: ServiceCall) -> None:
        await _handle_set_to_next_free_day(hass, call)

    async def sync_shopping_list(call: ServiceCall) -> ServiceResponse:
        result = await async_sync_shopping_list(hass, _get_active_runtime(hass))
        return result if call.return_response else None

    async def enrich_from_openfoodfacts(call: ServiceCall) -> ServiceResponse:
        result = await async_enrich_from_openfoodfacts(
            hass,
            _get_active_runtime(hass),
            dry_run=call.data["dry_run"],
            limit=call.data["limit"],
            include_calories=call.data["include_calories"],
            include_images=call.data["include_images"],
            exclude_product_groups=call.data["exclude_product_groups"],
            name_check=call.data["name_check"],
            confirm_barcodes=call.data["confirm_barcodes"],
        )
        return result if call.return_response else None

    hass.services.async_register(DOMAIN, "add_missing_ingredients", add_missing, schema=ADD_MISSING_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        "enrich_from_openfoodfacts",
        enrich_from_openfoodfacts,
        schema=ENRICH_OFF_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "sync_shopping_list",
        sync_shopping_list,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "set_to_next_free_day", set_next_free_day, schema=SET_NEXT_FREE_DAY_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = _prepare_runtime_config({**entry.data, **entry.options})
    _setup_daily_mealplan_sync(hass, entry)
    _setup_grocy_shopping_sync(hass, entry)
    _setup_openfoodfacts_sync(hass, entry)

    try:
        await _async_register_frontend(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Fehler bei der Frontend-Registrierung der Custom Card: %s", err)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

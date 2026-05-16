"""Sensor platform for Mealie Grocy Bridge."""
from datetime import timedelta, datetime
import logging
import re
import asyncio

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASICS = [
    "salz", "pfeffer", "wasser", "öl", "zucker", "mehl", "gewürz", "prise", "etwas",
    "kümmel", "basilikum", "cayennepfeffer", "chilli", "curry", "honig", "koriander",
    "kurkuma", "majoran", "meersalz", "muskat", "oregano", "paprikapulver",
    "petersilie", "schnittlauch", "thymian"
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    coordinator = MealieGrocyBridgeCoordinator(hass, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    # NEU: Coordinator für die __init__.py bereitstellen
    hass.data[DOMAIN]["coordinator"] = coordinator

    async_add_entities([MealieGrocySensor(coordinator, entry.entry_id)], True)


class MealieGrocyBridgeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mealie and Grocy data."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the coordinator."""
        self.entry_id = entry_id
        self.session = async_get_clientsession(hass)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )

    async def _fetch_recipe_details(self, semaphore, slug, mealie_url, headers):
        """Fetch full details for a single recipe with concurrency limit."""
        async with semaphore:
            try:
                async with self.session.get(f"{mealie_url}/api/recipes/{slug}", headers=headers, timeout=10) as res:
                    if res.status == 200:
                        return await res.json()
            except Exception as err:
                _LOGGER.error("Fehler beim Abrufen des Rezept-Details für %s: %s", slug, err)
            return None

    async def _async_update_data(self):
        """Fetch data from Grocy and Mealie and run matching algorithm."""
        config_entry_data = self.hass.data[DOMAIN][self.entry_id]

        grocy_url = config_entry_data[CONF_GROCY_URL].rstrip("/")
        if not grocy_url.startswith(("http://", "https://")):
            grocy_url = f"http://{grocy_url}"
            
        grocy_token = config_entry_data[CONF_GROCY_TOKEN]
        
        mealie_url = config_entry_data[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"
            
        mealie_token = config_entry_data[CONF_MEALIE_TOKEN]

        ui_exclusions = config_entry_data.get("excluded_foods_list", [])
        basics_to_ignore = [item.lower() for item in ui_exclusions] if ui_exclusions else DEFAULT_BASICS

        grocy_headers = {"GROCY-API-KEY": grocy_token}
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}

        # =====================================================================
        # 2. MEALIE SPEISEPLAN ABRUFEN
        # =====================================================================
        today = datetime.now().date()
        end_date = today + timedelta(days=8)
        mealplan_url = f"{mealie_url}/api/households/mealplans?startTime={today}&endTime={end_date}"
        
        planned_identifiers = set()
        invalid_keywords = {"none", "null", "string", ""}

        try:
            async with self.session.get(mealplan_url, headers=mealie_headers, timeout=10) as res:
                if res.status == 200:
                    raw_data = await res.json()
                    items = []
                    if isinstance(raw_data, list):
                        items = raw_data
                    elif isinstance(raw_data, dict):
                        items = raw_data.get("items", raw_data.get("data", []))
                    
                    if isinstance(items, list):
                        for plan in items:
                            if not isinstance(plan, dict):
                                continue
                            r_id = plan.get("recipeId")
                            if r_id:
                                s_id = str(r_id).strip().lower()
                                if s_id not in invalid_keywords and len(s_id) > 5:
                                    planned_identifiers.add(s_id)
                            recipe_obj = plan.get("recipe")
                            if isinstance(recipe_obj, dict):
                                for key in ["id", "slug"]:
                                    val = recipe_obj.get(key)
                                    if val:
                                        s_val = str(val).strip().lower()
                                        if s_val not in invalid_keywords and len(s_val) > 2:
                                            planned_identifiers.add(s_val)
        except Exception as err:
            _LOGGER.error("Fehler im Speiseplan-Filter: %s", err)

        # =====================================================================
        # 3. GROCY BESTAND ABRUFEN
        # =====================================================================
        try:
            async with self.session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=15) as res:
                if res.status != 200:
                    raise Exception(f"Grocy API Fehler: {res.status}")
                grocy_data = await res.json()
        except Exception as err:
            raise Exception(f"Verbindung zu Grocy fehlgeschlagen: {err}")

        grocy_products_map = {}
        in_one_month = today + timedelta(days=30)

        for item in (grocy_data or []):
            if isinstance(item, dict) and "product" in item:
                product_name = item.get("product", {}).get("name")
                if product_name:
                    orig_name = str(product_name).strip()
                    is_expiring_soon = False
                    bbd_str = item.get("best_before_date")
                    if bbd_str:
                        try:
                            if not bbd_str.startswith("2999"):
                                bbd_date = datetime.strptime(bbd_str, "%Y-%m-%d").date()
                                if bbd_date <= in_one_month:
                                    is_expiring_soon = True
                        except ValueError:
                            pass
                    grocy_products_map[orig_name.lower()] = {"orig_name": orig_name, "expiring": is_expiring_soon}

        # =====================================================================
        # 4. MEALIE REZEPTE ABRUFEN
        # =====================================================================
        try:
            async with self.session.get(f"{mealie_url}/api/recipes?perPage=-1", headers=mealie_headers, timeout=15) as res:
                if res.status != 200:
                    raise Exception(f"Mealie API Fehler: {res.status}")
                mealie_data = await res.json()
        except Exception as err:
            raise Exception(f"Verbindung zu Mealie fehlgeschlagen: {err}")

        recipes_list = mealie_data.get("items", [])
        
        semaphore = asyncio.Semaphore(10)
        tasks = [
            self._fetch_recipe_details(semaphore, r.get("slug"), mealie_url, mealie_headers)
            for r in recipes_list if r.get("slug")
        ]
        full_recipes = await asyncio.gather(*tasks)
        full_recipes = [r for r in full_recipes if r is not None]

        # =====================================================================
        # 5. MATCHING ALGORITHMUS (ULTRA-INTELLIGENTER ABGLEICH)
        # =====================================================================
        results = []

        for recipe in full_recipes:
            if not isinstance(recipe, dict):
                continue
                
            r_id = recipe.get("id")
            r_recipe_id = recipe.get("recipeId")
            r_slug = recipe.get("slug")
            
            is_planned = False
            for identifier in [r_id, r_recipe_id, r_slug]:
                if identifier:
                    s_ident = str(identifier).strip().lower()
                    if s_ident in planned_identifiers:
                        is_planned = True
                        break
            
            if is_planned:
                continue

            all_ingredients = recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []
            
            relevant_ingredients = []
            for ing in all_ingredients:
                if not isinstance(ing, dict):
                    continue
                text = (ing.get("note") or ing.get("display") or ing.get("originalText") or "").lower()
                if text and not any(basic in text for basic in basics_to_ignore):
                    relevant_ingredients.append(ing)

                if not relevant_ingredients:
                    continue

            match_count = 0
            has_expiring_ingredient = False
            matching_details = []
            missing_details = []

            for ing in relevant_ingredients:
                ing_original_text = ing.get("display") or ing.get("note") or ing.get("originalText") or ""
                ing_text_low = str(ing_original_text).lower()
                
                # Mealie-Wörter splitten (Zahlen und Mini-Wörter ignorieren)
                ing_words = [w for w in re.split(r"[\s,()./]+", ing_text_low) if len(w) > 2 and not w.isdigit()]

                found_product_info = None
                
                for stock_low, info in grocy_products_map.items():
                    # 1. DIREKT-MATCH (Exakter Treffer im Text mit Wortgrenzen)
                    # Verhindert z.B. dass "Senf" fälschlicherweise in "Senfsamen" matcht
                    # Aber erlaubt "Senf" in "Mittelscharfer Senf"
                    if re.search(r'\b' + re.escape(stock_low) + r'\b', ing_text_low):
                        found_product_info = info
                        break
                        
                    # 2. SPLITTING FÜR BINDESTRICHE (z.B. "Nudeln - Farfalle")
                    stock_parts = [p.strip() for p in re.split(r"[\-,._]+", stock_low) if len(p.strip()) > 2]
                    if stock_parts and stock_parts[0] in ing_words:
                        found_product_info = info
                        break
                        
                    # 3. TEILWORT-MATCH FÜR COMPREHENSIVE COMPOSITION (z.B. Mealie: "Mehl" -> Grocy: "Weizenmehl")
                    # Optimierung: Matcht nur, wenn das Rezept-Wort am ENDE des Grocy-Produktworts steht 
                    # oder ein eigenständiges Wort darin bildet (z.B. "weizenmehl", "senf", "dijonsenf").
                    # Verhindert Fehlmatches wenn es am Anfang steht und weitergeht (z.B. "senfsamen", "senfkörner").
                    for word in ing_words:
                        if len(word) >= 4:
                            # Erstellt eine Regex die prüft ob das Wort am Ende eines Wortes steht 
                            # (z.B. "weizenmehl" für "mehl" oder "dijonsenf" für "senf")
                            # aber NICHT wenn danach noch Buchstaben folgen ("senfsamen")
                            if re.search(re.escape(word) + r'\b', stock_low):
                                found_product_info = info
                                break
                    if found_product_info:
                        break

                if found_product_info:
                    match_count += 1
                    matching_details.append(found_product_info["orig_name"])
                    if found_product_info["expiring"]:
                        has_expiring_ingredient = True
                else:
                    missing_details.append(ing_original_text)

            if match_count > 0:
                score = round((match_count / len(relevant_ingredients)) * 100)
                if has_expiring_ingredient:
                    score += 15
                    if score > 100:
                        score = 100

                ui_recipe_id = str(r_recipe_id or r_id).strip()

                results.append({
                    "recipeId": ui_recipe_id,
                    "recipeName": recipe.get("name", "Unbekanntes Rezept"),
                    "matchScore": score,
                    "matchCount": match_count,
                    "relevantTotal": len(relevant_ingredients),
                    "matchingIngredients": list(set(matching_details)),
                    "missingIngredients": missing_details,
                    "url": f"{mealie_url}/g/home/r/{r_slug or ''}",
                    "hasExpiring": has_expiring_ingredient
                })

        results.sort(key=lambda x: x["matchScore"], reverse=True)
        return results


class MealieGrocySensor(CoordinatorEntity, SensorEntity):
    """Representation of the Mealie Grocy Bridge Sensor."""

    def __init__(self, coordinator: MealieGrocyBridgeCoordinator, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_suggestions"
        self._attr_name = "Mealie Grocy Kochvorschläge"
        self._attr_icon = "mdi:chef-hat"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "recipes": self.coordinator.data if self.coordinator.data else [],
            "markdown_suggestions": ""
        }

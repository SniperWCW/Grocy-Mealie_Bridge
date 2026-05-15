"""Sensor platform for Mealie Grocy Bridge."""
from datetime import timedelta
import logging
import re
import asyncio
import urllib.parse

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

BASICS_TO_IGNORE = [
    "salz", "pfeffer", "wasser", "öl", "zucker", "mehl", "gewürz", "prise", "etwas",
    "kümmel", "sasilikum", "cayennepfeffer", "chilli", "curry", "honig", "koriander",
    "kurkuma", "majoran", "meersalz", "muskat", "oregano", "paprikapulver",
    "petersilie", "schnittlauch", "thymian"
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    config = entry.data
    coordinator = MealieGrocyBridgeCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([MealieGrocySensor(coordinator, entry.entry_id)], True)


class MealieGrocyBridgeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mealie and Grocy data."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the coordinator."""
        self.config = config
        self.session = async_get_clientsession(hass)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=60),
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
        grocy_url = self.config[CONF_GROCY_URL].rstrip("/")
        if not grocy_url.startswith(("http://", "https://")):
            grocy_url = f"http://{grocy_url}"
            
        grocy_token = self.config[CONF_GROCY_TOKEN]
        
        mealie_url = self.config[CONF_MEALIE_URL].rstrip("/")
        if not mealie_url.startswith(("http://", "https://")):
            mealie_url = f"http://{mealie_url}"
            
        mealie_token = self.config[CONF_MEALIE_TOKEN]

        grocy_headers = {"GROCY-API-KEY": grocy_token}
        mealie_headers = {"Authorization": f"Bearer {mealie_token}"}

        try:
            async with self.session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=15) as res:
                if res.status != 200:
                    hash_err = await res.text()
                    raise Exception(f"Grocy API Fehler: {res.status} - {hash_err}")
                grocy_data = await res.json()
        except Exception as err:
            raise Exception(f"Verbindung zu Grocy fehlgeschlagen: {err}")

        grocy_products_map = {}
        for item in (grocy_data or []):
            if isinstance(item, dict) and "product" in item:
                product_name = item.get("product", {}).get("name")
                if product_name:
                    orig_name = str(product_name).strip()
                    grocy_products_map[orig_name.lower()] = orig_name

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

        results = []

        for recipe in full_recipes:
            if not isinstance(recipe, dict):
                continue
                
            all_ingredients = recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []
            
            relevant_ingredients = []
            for ing in all_ingredients:
                if not isinstance(ing, dict):
                    continue
                text = (ing.get("note") or ing.get("display") or ing.get("originalText") or "").lower()
                if text and not any(basic in text for basic in BASICS_TO_IGNORE):
                    relevant_ingredients.append(ing)

            if not relevant_ingredients:
                continue

            match_count = 0
            matching_details = []
            missing_details = []

            for ing in relevant_ingredients:
                ing_original_text = ing.get("display") or ing.get("note") or ing.get("originalText") or ""
                ing_text_low = str(ing_original_text).lower()
                ing_words = [w for w in re.split(r"[\s,()./]+", ing_text_low) if len(w) > 2]

                found_stock_display = None
                
                for stock_low, stock_orig in grocy_products_map.items():
                    if stock_low in ing_words or \
                       any(word == stock_low for word in ing_words) or \
                       (len(stock_low) > 4 and stock_low in ing_text_low):
                        found_stock_display = stock_orig
                        break

                if found_stock_display:
                    match_count += 1
                    matching_details.append(found_stock_display)
                else:
                    missing_details.append(ing_original_text)

            if match_count > 0:
                score = round((match_count / len(relevant_ingredients)) * 100)
                results.append({
                    "recipeName": recipe.get("name", "Unbekanntes Rezept"),
                    "matchScore": score,
                    "matchCount": match_count,
                    "relevantTotal": len(relevant_ingredients),
                    "matchingIngredients": list(set(matching_details)),
                    "missingIngredients": missing_details,
                    "url": f"{mealie_url}/g/home/r/{recipe.get('slug', '')}"
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
        """Return the number of total matching recipes."""
        return len(self.coordinator.data) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return device state attributes."""
        if not self.coordinator.data:
            return {"recipes": [], "markdown_suggestions": "Keine passenden Rezepte gefunden. 🍕"}

        top_recipes = self.coordinator.data[:5]
        
        markdown = "### 🍳 Koch-Vorschläge für heute\n"
        markdown += "*Abgleich mit deinem Grocy-Bestand*\n"
        markdown += "---\n\n"

        for r in top_recipes:
            markdown += f"**{r['recipeName'].upper()}**\n"
            markdown += f"📊 Score: **{r['matchScore']}%**\n"
            
            formatted_ingredients = [str(i).capitalize() for i in r['matchingIngredients']]
            markdown += f"✅ Vorhanden: `{', '.join(formatted_ingredients)}`\n"
            
            if r["missingIngredients"]:
                ingredients_str = ", ".join(r["missingIngredients"])
                markdown += f"🛒 Einkaufen: *{ingredients_str}*\n"
                
            markdown += f"👉 [Rezept öffnen]({r['url']})\n\n"
            markdown += "---\n"

        markdown += "*🤖 Generiert über Mealie-Grocy Bridge Integration*"

        return {
            "recipes": top_recipes,
            "markdown_suggestions": markdown
        }

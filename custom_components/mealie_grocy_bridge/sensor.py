"""Sensor platform for Mealie Grocy Bridge."""
from datetime import timedelta, datetime
import logging
import re
import asyncio

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

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

    # Coordinator für die __init__.py bereitstellen
    # hass.data[DOMAIN]["coordinator"] = coordinator Update 18.05.2026
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    async_add_entities([MealieGrocySensor(coordinator, entry.entry_id)], True)


class MealieGrocyBridgeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mealie and Grocy data."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the coordinator."""
        self.entry_id = entry_id
        self.session = async_get_clientsession(hass)
        self.current_week_mealplan = []
        self.current_week_range = {"start": None, "end": None}
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )

    @staticmethod
    def _get_current_week_bounds(today):
        """Return the current Saturday-based week bounds."""
        days_since_saturday = (today.weekday() - 5) % 7
        week_start = today - timedelta(days=days_since_saturday)
        week_end = week_start + timedelta(days=7)
        return week_start, week_end

    @staticmethod
    def _extract_mealplan_items(raw_data):
        """Normalize mealplan API payloads to a list of items."""
        if isinstance(raw_data, list):
            return raw_data
        if isinstance(raw_data, dict):
            return raw_data.get("items", raw_data.get("data", []))
        return []

    @staticmethod
    def _extract_recipe_name(plan):
        """Extract a human-friendly recipe name from a mealplan entry."""
        recipe_obj = plan.get("recipe")
        if isinstance(recipe_obj, dict):
            for key in ("name", "title"):
                value = recipe_obj.get(key)
                if value:
                    return str(value).strip()
        for key in ("title", "text", "note"):
            value = plan.get(key)
            if value:
                return str(value).strip()
        return "Unbekannt"

    @staticmethod
    def _normalize_duration(value):
        """Normalize duration values from Mealie into displayable text."""
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return f"{int(value)} min"
        text_value = str(value).strip()
        if not text_value:
            return None
        return text_value

    @staticmethod
    def _extract_recipe_image(plan, mealie_url):
        """Extract a recipe image URL from a mealplan entry when available."""
        recipe_obj = plan.get("recipe")
        if not isinstance(recipe_obj, dict):
            return None

        for key in ("image", "imageUrl", "recipeImage", "thumbnail"):
            value = recipe_obj.get(key)
            if isinstance(value, str) and value.strip():
                if value.startswith(("http://", "https://")):
                    return value.strip()
                return f"{mealie_url}/{value.lstrip('/')}"

        recipe_asset = recipe_obj.get("recipeAsset")
        if isinstance(recipe_asset, dict):
            for key in ("image", "url", "path"):
                value = recipe_asset.get(key)
                if isinstance(value, str) and value.strip():
                    if value.startswith(("http://", "https://")):
                        return value.strip()
                    return f"{mealie_url}/{value.lstrip('/')}"

        return None

    @classmethod
    def _extract_mealplan_recipe_meta(cls, plan, mealie_url):
        """Extract image and timing metadata from a mealplan recipe."""
        recipe_obj = plan.get("recipe")
        recipe_meta = {
            "imageUrl": cls._extract_recipe_image(plan, mealie_url),
            "prepTime": None,
            "cookTime": None,
            "totalTime": None,
        }

        if not isinstance(recipe_obj, dict):
            return recipe_meta

        recipe_meta["prepTime"] = cls._normalize_duration(
            recipe_obj.get("prepTime") or recipe_obj.get("prepTimeMinutes")
        )
        recipe_meta["cookTime"] = cls._normalize_duration(
            recipe_obj.get("cookTime")
            or recipe_obj.get("performTime")
            or recipe_obj.get("performTimeMinutes")
        )
        recipe_meta["totalTime"] = cls._normalize_duration(
            recipe_obj.get("totalTime") or recipe_obj.get("totalTimeMinutes")
        )

        return recipe_meta

    @staticmethod
    def _clean_basic_ingredient(text_low, fallback):
        """Normalize basic ingredients by stripping amounts and units."""
        cleaned_text = str(text_low or "").lower().replace("-", " ").strip()
        cleaned_text = re.sub(r"\s+", " ", cleaned_text)

        quantity_pattern = (
            r"^\s*(?:"
            r"\d+\s*/\s*\d+|"
            r"\d+[.,]?\d*|"
            r"[¼½¾⅓⅔⅛⅜⅝⅞]"
            r")\s*"
        )
        unit_pattern = (
            r"^\s*(?:tl|el|g|kg|mg|ml|cl|dl|l|liter|bund|stück|stueck|stck|"
            r"zehe|zehen|prise|prisen|becher|dose|päckchen|paeckchen)\b\s*"
        )

        changed = True
        while cleaned_text and changed:
            previous = cleaned_text
            cleaned_text = re.sub(quantity_pattern, "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(unit_pattern, "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = cleaned_text.strip(" ,.")
            changed = cleaned_text != previous

        if not cleaned_text or len(cleaned_text) <= 2:
            cleaned_text = fallback

        return cleaned_text.strip().capitalize()

    async def _fetch_recipe_details(self, semaphore, slug, mealie_url, headers):
        """Fetch full details for a single recipe with concurrency limit and pacing."""
        async with semaphore:
            try:
                async with self.session.get(f"{mealie_url}/api/recipes/{slug}", headers=headers, timeout=10) as res:
                    if res.status == 200:
                        # Ein ganz kurzes Delay nach dem erfolgreichen Request,
                        # um die API und die DB-Verbindungen zu entlasten
                        await asyncio.sleep(0.05)
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
        today = dt_util.now().date()
        week_start, week_end = self._get_current_week_bounds(today)
        mealplan_url = f"{mealie_url}/api/households/mealplans?startTime={week_start}&endTime={week_end}"
        
        planned_identifiers = set()
        invalid_keywords = {"none", "null", "string", ""}
        weekly_mealplan = []

        try:
            async with self.session.get(mealplan_url, headers=mealie_headers, timeout=10) as res:
                if res.status == 200:
                    raw_data = await res.json()
                    items = self._extract_mealplan_items(raw_data)
                    
                    if isinstance(items, list):
                        for plan in items:
                            if not isinstance(plan, dict):
                                continue
                            plan_date_raw = plan.get("date") or plan.get("startTime") or plan.get("startDate")
                            if not plan_date_raw:
                                continue

                            try:
                                plan_date = datetime.fromisoformat(
                                    str(plan_date_raw).replace("Z", "+00:00")
                                ).date()
                            except ValueError:
                                try:
                                    plan_date = datetime.strptime(str(plan_date_raw)[:10], "%Y-%m-%d").date()
                                except ValueError:
                                    continue

                            if plan_date >= today:
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

                            if not (week_start <= plan_date <= week_end):
                                continue

                            recipe_meta = self._extract_mealplan_recipe_meta(plan, mealie_url)

                            weekly_mealplan.append({
                                "date": plan_date.isoformat(),
                                "dateLabel": plan_date.strftime("%d.%m.%Y"),
                                "weekday": plan_date.strftime("%A"),
                                "entryType": str(plan.get("entryType", "meal")).strip(),
                                "recipeName": self._extract_recipe_name(plan),
                                "imageUrl": recipe_meta["imageUrl"],
                                "prepTime": recipe_meta["prepTime"],
                                "cookTime": recipe_meta["cookTime"],
                                "totalTime": recipe_meta["totalTime"],
                            })
        except Exception as err:
            _LOGGER.error("Fehler im Speiseplan-Filter: %s", err)

        weekly_mealplan.sort(key=lambda item: (item["date"], item["entryType"], item["recipeName"]))
        self.current_week_mealplan = weekly_mealplan
        self.current_week_range = {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
        }

        # =====================================================================
        # 3. GROCY BESTAND ABRUFEN
        # =====================================================================
        try:
            async with self.session.get(f"{grocy_url}/api/stock", headers=grocy_headers, timeout=15) as res:
                if res.status != 200:
                    raise UpdateFailed(f"Grocy API Fehler: {res.status}")
                grocy_data = await res.json()
        except Exception as err:
            raise UpdateFailed(f"Verbindung zu Grocy fehlgeschlagen: {err}")

        grocy_products_map = {}
        in_one_month = today + timedelta(days=30)

        for item in (grocy_data or []):
            if isinstance(item, dict) and "product" in item:
                product_name = item.get("product", {}).get("name")

                if product_name:
                    orig_name = str(product_name).strip()

                    # Standardstatus
                    ingredient_status = "normal"

                    bbd_str = item.get("best_before_date")

                    if bbd_str:
                        try:
                            if not bbd_str.startswith("2999"):
                                bbd_date = datetime.strptime(
                                    bbd_str,
                                    "%Y-%m-%d"
                                ).date()

                                # Bereits abgelaufen
                                if bbd_date < today:
                                    ingredient_status = "expired"

                                # Läuft bald ab
                                elif bbd_date <= in_one_month:
                                    ingredient_status = "expiring"

                        except ValueError:
                            pass

                    grocy_products_map[orig_name.lower()] = {
                        "orig_name": orig_name,
                        "status": ingredient_status,
                        "regex": re.compile(
                            r'\b' + re.escape(orig_name.lower()) + r'\b'
                        )
                    }

# =====================================================================
        # 4. MEALIE REZEPTE ABRUFEN
        # =====================================================================
        try:
            async with self.session.get(f"{mealie_url}/api/recipes?perPage=-1", headers=mealie_headers, timeout=15) as res:
                if res.status != 200:
                    raise UpdateFailed(f"Mealie API Fehler: {res.status}")
                mealie_data = await res.json()
        except Exception as err:
            raise UpdateFailed(f"Verbindung zu Mealie fehlgeschlagen: {err}")

        recipes_list = mealie_data.get("items", [])
        
        # Auf 5 reduzieren – das schont Ressourcen und reicht bei 30 Min Update-Intervall locker
        semaphore = asyncio.Semaphore(5)
        tasks = [
            self._fetch_recipe_details(semaphore, r.get("slug"), mealie_url, mealie_headers)
            for r in recipes_list if r.get("slug")
        ]
        full_recipes = await asyncio.gather(*tasks, return_exceptions=True)
        full_recipes = [
            r for r in full_recipes
            if r is not None and not isinstance(r, Exception)
    ]

        # =====================================================================
        # 5. MATCHING ALGORITHMUS
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
            basic_ingredients_details = []

            for ing in all_ingredients:
                if not isinstance(ing, dict):
                    continue
                display_text = ing.get("display") or ing.get("note") or ing.get("originalText") or ""
                text_low = display_text.lower()
                
                # Prüfen, ob die Zutat zu den Basics gehört
                matched_basic = None
                for basic in basics_to_ignore:
                    if basic in text_low:
                        matched_basic = basic
                        break

                if matched_basic:
                    basic_ingredients_details.append(
                        self._clean_basic_ingredient(text_low, matched_basic)
                    )
                    continue
                    # REINIGUNGS-LOGIK FÜR BASICS:
                    cleaned_text = re.sub(
                        r'^\s*[\d½⅓¼⅕⅙⅛.,\s]+\s*(tl|el|g|kg|ml|l|Liter|bund|stück|stck|zehe|zehen)?\s*',
                        '',
                        text_low,
                        flags=re.IGNORECASE
                    )
                    cleaned_text = cleaned_text.replace('-', ' ').strip()
                    
                    final_basic_name = cleaned_text if len(cleaned_text) > 2 else matched_basic
                    basic_ingredients_details.append(final_basic_name.strip().capitalize())
                else:
                    if text_low:
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
                
                # Extrahiere Wörter aus der Rezept-Zutat
                ing_words = [w for w in re.split(r"[\s,()./]+", ing_text_low) if len(w) > 2 and not w.isdigit()]

                found_product_info = None
                
                # -----------------------------------------------------------------
                # DURCHLAUF 1: STRIKTE DIREKT-MATCHES (Wort-Grenzen)
                # -----------------------------------------------------------------
                for stock_low, info in grocy_products_map.items():
                    # Harte Ausschlüsse für Suppen/Nudeln/Reis vs. Fleisch
                    if any(nw in stock_low for nw in ["yumyum", "nudeln", "ramen", "reis"]):
                        if any(fw in ing_text_low for fw in ["wings", "schenkel", "filet", "keulen"]):
                            continue
                        # Verhindert Fehlmatches im ersten Durchlauf auf allgemeine Zutaten
                        if any(kw in stock_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                            if not any(kw in ing_text_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                                continue

                    if info["regex"].search(ing_text_low):
                        found_product_info = info
                        break
                        
                # -----------------------------------------------------------------
                # DURCHLAUF 2: INTELLIGENTES SELEKTIVES MATCHING
                # -----------------------------------------------------------------
                if not found_product_info:
                    for stock_low, info in grocy_products_map.items():
                        if any(nw in stock_low for nw in ["yumyum", "nudeln", "ramen", "reis"]):
                            if any(fw in ing_text_low for fw in ["wings", "schenkel", "filet", "keulen"]):
                                continue

                        # Zerlege den Grocy-Namen in einzelne Wörter
                        stock_words = [p.strip() for p in re.split(r"[\s\-,._()]+", stock_low) if len(p.strip()) > 2]
                        if not stock_words:
                            continue

                        # SPEZIALFALL CHICKEN: Verhindert, dass "Chicken Wings" auf "Chicken Nuggets" matcht
                        if "chicken" in ing_words and "chicken" in stock_words:
                            if "wings" in ing_words and "wings" not in stock_words:
                                continue
                            if "nuggets" in ing_words and "nuggets" not in stock_words:
                                continue

                        # SPEZIALFALL NUDELN / RAMEN / YUMYUM / REIS
                        if any(nw in stock_low for nw in ["nudeln", "ramen", "yumyum", "reis"]):
                            if not any(nw in ing_text_low for nw in ["nudeln", "ramen", "suppe", "yumyum", "reis"]):
                                continue
                            
                            # HARTER AUSSCHLUSS FÜR HOCHSPEZIFISCHE ASIA-PRODUKTE
                            if any(kw in stock_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                                if not any(kw in ing_text_low for kw in ["nouilles", "spring", "asia", "happiness"]):
                                    continue

                            if "wan-tan" in stock_low and "wan-tan" not in ing_text_low:
                                continue

                        # Allgemeiner Abgleich mit Plural-Toleranz
                        match_found = False
                        for word in ing_words:
                            for s_word in stock_words:
                                if word == s_word or word + "n" == s_word or word + "s" == s_word or word + "en" == s_word or s_word + "n" == word or s_word + "s" == word:
                                    found_product_info = info
                                    match_found = True
                                    break
                            if match_found:
                                break
                        if match_found:
                            break

                # -----------------------------------------------------------------

                if found_product_info:
                    match_count += 1
                    matching_details.append({
                        "name": found_product_info["orig_name"],
                        "status": found_product_info["status"]
                    })

                    if found_product_info["status"] in ["expired", "expiring"]:
                        has_expiring_ingredient = True
                else:
                    # Erstes echtes Wort/Zutat sauber formatieren
                    cleaned_ing = str(ing_original_text).strip()
                    if cleaned_ing:
                        formatted_ing = cleaned_ing[0].upper() + cleaned_ing[1:]
                        missing_details.append(formatted_ing)

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
                    "matchingIngredients": matching_details,
                    "missingIngredients": missing_details,
                    "basicIngredients": list(set(basic_ingredients_details)),
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
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "recipes": self.coordinator.data if self.coordinator.data else [],
            "current_week_mealplan": self.coordinator.current_week_mealplan,
            "current_week_range": self.coordinator.current_week_range,
        }

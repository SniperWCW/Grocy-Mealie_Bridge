"""Constants and small shared helpers for the Mealie Grocy Bridge integration."""

from __future__ import annotations

from datetime import date, datetime

import aiohttp

DOMAIN = "mealie_grocy_bridge"

# Konfigurations-Keys
CONF_MEALIE_URL = "mealie_url"
CONF_MEALIE_TOKEN = "mealie_token"
CONF_GROCY_URL = "grocy_url"
CONF_GROCY_TOKEN = "grocy_token"
CONF_EXCLUDED_FOODS = "excluded_foods"
CONF_TODO_ENTITY = "todo_entity"
CONF_DAILY_MEALPLAN_SYNC_ENABLED = "daily_mealplan_sync_enabled"
CONF_DAILY_MEALPLAN_SYNC_TIME = "daily_mealplan_sync_time"
CONF_MEALPLAN_WINDOW_MODE = "mealplan_window_mode"
CONF_MEALPLAN_WINDOW_DAYS = "mealplan_window_days"
CONF_MEALPLAN_SYNC_MODE = "mealplan_sync_mode"
CONF_MEALPLAN_SYNC_WEEKDAY = "mealplan_sync_weekday"
CONF_MEALPLAN_SYNC_DAYS_AHEAD = "mealplan_sync_days_ahead"
CONF_GROCY_SHOPPING_SYNC_ENABLED = "grocy_shopping_sync_enabled"
CONF_GROCY_SHOPPING_SYNC_INTERVAL = "grocy_shopping_sync_interval"
CONF_GROCY_SHOPPING_AFTER = "grocy_shopping_after_transfer"

GROCY_SHOPPING_AFTER_DELETE = "delete"
GROCY_SHOPPING_AFTER_MARK_DONE = "mark_done"
DEFAULT_GROCY_SHOPPING_SYNC_INTERVAL = 15

MEALPLAN_WINDOW_CURRENT_WEEK = "current_week"
MEALPLAN_WINDOW_NEXT_WEEK = "next_week"
MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK = "current_and_next_week"
MEALPLAN_WINDOW_TODAY_PLUS_DAYS = "today_plus_days"

MEALPLAN_SYNC_MODE_DAILY = "daily_today"
MEALPLAN_SYNC_MODE_WEEKLY = "weekly_next_days"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

WEEKDAY_NAMES_DE = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


def normalize_base_url(url: str) -> str:
    """Strip trailing slashes and add a scheme when missing."""
    url = str(url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url


def parse_mealplan_date(plan: dict) -> date | None:
    """Extract the calendar date from a Mealie meal plan entry."""
    if not isinstance(plan, dict):
        return None
    raw_value = plan.get("date") or plan.get("startTime") or plan.get("startDate")
    text_value = str(raw_value or "").strip()
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text_value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

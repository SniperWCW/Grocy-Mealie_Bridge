"""Config flow for Mealie Grocy Bridge integration."""

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_DAILY_MEALPLAN_SYNC_ENABLED,
    CONF_DAILY_MEALPLAN_SYNC_TIME,
    CONF_EXCLUDED_FOODS,
    CONF_GROCY_TOKEN,
    CONF_GROCY_URL,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    CONF_MEALPLAN_SYNC_DAYS_AHEAD,
    CONF_MEALPLAN_SYNC_MODE,
    CONF_MEALPLAN_SYNC_WEEKDAY,
    CONF_MEALPLAN_WINDOW_DAYS,
    CONF_MEALPLAN_WINDOW_MODE,
    CONF_TODO_ENTITY,
    DOMAIN,
    MEALPLAN_SYNC_MODE_DAILY,
    MEALPLAN_SYNC_MODE_WEEKLY,
    MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK,
    MEALPLAN_WINDOW_CURRENT_WEEK,
    MEALPLAN_WINDOW_NEXT_WEEK,
    MEALPLAN_WINDOW_TODAY_PLUS_DAYS,
)

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DEFAULT_EXCLUDED_FOODS = (
    "salz, pfeffer, wasser, öl, zucker, mehl, gewürz, kümmel, basilikum, "
    "cayennepfeffer, chilli, curry, honig, koriander, kurkuma, majoran, "
    "meersalz, muskat, oregano, paprikapulver, petersilie, schnittlauch, thymian"
)

MEALPLAN_WINDOW_OPTIONS = {
    MEALPLAN_WINDOW_CURRENT_WEEK: MEALPLAN_WINDOW_CURRENT_WEEK,
    MEALPLAN_WINDOW_NEXT_WEEK: MEALPLAN_WINDOW_NEXT_WEEK,
    MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK: MEALPLAN_WINDOW_CURRENT_AND_NEXT_WEEK,
    MEALPLAN_WINDOW_TODAY_PLUS_DAYS: MEALPLAN_WINDOW_TODAY_PLUS_DAYS,
}

SYNC_MODE_OPTIONS = {
    MEALPLAN_SYNC_MODE_DAILY: MEALPLAN_SYNC_MODE_DAILY,
    MEALPLAN_SYNC_MODE_WEEKLY: MEALPLAN_SYNC_MODE_WEEKLY,
}

WEEKDAY_OPTIONS = {
    "monday": "monday",
    "tuesday": "tuesday",
    "wednesday": "wednesday",
    "thursday": "thursday",
    "friday": "friday",
    "saturday": "saturday",
    "sunday": "sunday",
}


def _is_valid_time_value(value: str) -> bool:
    """Return True when the provided value matches HH:MM."""
    return bool(TIME_PATTERN.match(str(value or "").strip()))


def _coerce_int(value, default: int) -> int:
    """Convert UI values to integers with a safe default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validate_user_input(user_input: dict) -> dict:
    """Validate configurable scheduling and meal plan window settings."""
    errors = {}

    if not _is_valid_time_value(user_input.get(CONF_DAILY_MEALPLAN_SYNC_TIME, "07:00")):
        errors[CONF_DAILY_MEALPLAN_SYNC_TIME] = "invalid_time"

    mealplan_window_mode = user_input.get(
        CONF_MEALPLAN_WINDOW_MODE, MEALPLAN_WINDOW_CURRENT_WEEK
    )
    mealplan_window_days = _coerce_int(user_input.get(CONF_MEALPLAN_WINDOW_DAYS, 7), 7)
    if (
        mealplan_window_mode == MEALPLAN_WINDOW_TODAY_PLUS_DAYS
        and not 0 <= mealplan_window_days <= 14
    ):
        errors[CONF_MEALPLAN_WINDOW_DAYS] = "invalid_days_range"

    sync_mode = user_input.get(CONF_MEALPLAN_SYNC_MODE, MEALPLAN_SYNC_MODE_DAILY)
    sync_days_ahead = _coerce_int(
        user_input.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7), 7
    )
    if sync_mode == MEALPLAN_SYNC_MODE_WEEKLY and not 1 <= sync_days_ahead <= 14:
        errors[CONF_MEALPLAN_SYNC_DAYS_AHEAD] = "invalid_days_ahead"

    return errors


def _build_schema_fields(values: dict, todo_options: dict) -> dict:
    """Build the shared schema fields for setup and options."""
    schema_fields = {
        vol.Required(
            CONF_MEALIE_URL,
            default=values.get(CONF_MEALIE_URL, "http://10.11.12.200:9000"),
        ): str,
        vol.Required(CONF_MEALIE_TOKEN, default=values.get(CONF_MEALIE_TOKEN, "")): str,
        vol.Required(
            CONF_GROCY_URL,
            default=values.get(CONF_GROCY_URL, "http://10.11.12.172:9283"),
        ): str,
        vol.Required(CONF_GROCY_TOKEN, default=values.get(CONF_GROCY_TOKEN, "")): str,
        vol.Optional(
            CONF_EXCLUDED_FOODS,
            default=values.get(CONF_EXCLUDED_FOODS, DEFAULT_EXCLUDED_FOODS),
        ): str,
        vol.Optional(
            CONF_MEALPLAN_WINDOW_MODE,
            default=values.get(CONF_MEALPLAN_WINDOW_MODE, MEALPLAN_WINDOW_CURRENT_WEEK),
        ): vol.In(MEALPLAN_WINDOW_OPTIONS),
        vol.Optional(
            CONF_MEALPLAN_WINDOW_DAYS,
            default=_coerce_int(values.get(CONF_MEALPLAN_WINDOW_DAYS, 7), 7),
        ): int,
        vol.Optional(
            CONF_DAILY_MEALPLAN_SYNC_ENABLED,
            default=values.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED, False),
        ): bool,
        vol.Optional(
            CONF_DAILY_MEALPLAN_SYNC_TIME,
            default=values.get(CONF_DAILY_MEALPLAN_SYNC_TIME, "07:00"),
        ): str,
        vol.Optional(
            CONF_MEALPLAN_SYNC_MODE,
            default=values.get(CONF_MEALPLAN_SYNC_MODE, MEALPLAN_SYNC_MODE_DAILY),
        ): vol.In(SYNC_MODE_OPTIONS),
        vol.Optional(
            CONF_MEALPLAN_SYNC_WEEKDAY,
            default=values.get(CONF_MEALPLAN_SYNC_WEEKDAY, "sunday"),
        ): vol.In(WEEKDAY_OPTIONS),
        vol.Optional(
            CONF_MEALPLAN_SYNC_DAYS_AHEAD,
            default=_coerce_int(values.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7), 7),
        ): int,
    }

    current_todo = values.get(CONF_TODO_ENTITY, "")
    if todo_options:
        todo_default = (
            current_todo if current_todo in todo_options else next(iter(todo_options))
        )
        schema_fields[vol.Optional(CONF_TODO_ENTITY, default=todo_default)] = vol.In(
            todo_options
        )
    else:
        schema_fields[vol.Optional(CONF_TODO_ENTITY, default=current_todo)] = str

    return schema_fields


class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle first-time setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            errors = _validate_user_input(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Mealie Grocy Bridge",
                    data=user_input,
                )

        todo_entities = self.hass.states.async_entity_ids("todo")
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}
        schema_fields = _build_schema_fields(user_input or {}, todo_options)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return MealieGrocyBridgeOptionsFlowHandler()


class MealieGrocyBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the integration options flow."""

    async def async_step_init(self, user_input=None):
        """Show and persist the options form."""
        if user_input is not None:
            errors = _validate_user_input(user_input)
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_options_schema(user_input),
                    errors=errors,
                )
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data
        values = {
            CONF_MEALIE_URL: options.get(CONF_MEALIE_URL) or data.get(CONF_MEALIE_URL) or "",
            CONF_MEALIE_TOKEN: options.get(CONF_MEALIE_TOKEN) or data.get(CONF_MEALIE_TOKEN) or "",
            CONF_GROCY_URL: options.get(CONF_GROCY_URL) or data.get(CONF_GROCY_URL) or "",
            CONF_GROCY_TOKEN: options.get(CONF_GROCY_TOKEN) or data.get(CONF_GROCY_TOKEN) or "",
            CONF_EXCLUDED_FOODS: options.get(CONF_EXCLUDED_FOODS)
            or data.get(CONF_EXCLUDED_FOODS)
            or DEFAULT_EXCLUDED_FOODS,
            CONF_TODO_ENTITY: options.get(CONF_TODO_ENTITY) or data.get(CONF_TODO_ENTITY) or "",
            CONF_MEALPLAN_WINDOW_MODE: options.get(CONF_MEALPLAN_WINDOW_MODE)
            or data.get(CONF_MEALPLAN_WINDOW_MODE)
            or MEALPLAN_WINDOW_CURRENT_WEEK,
            CONF_MEALPLAN_WINDOW_DAYS: _coerce_int(
                options.get(
                    CONF_MEALPLAN_WINDOW_DAYS,
                    data.get(CONF_MEALPLAN_WINDOW_DAYS, 7),
                ),
                7,
            ),
            CONF_DAILY_MEALPLAN_SYNC_ENABLED: options.get(
                CONF_DAILY_MEALPLAN_SYNC_ENABLED,
                data.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED, False),
            ),
            CONF_DAILY_MEALPLAN_SYNC_TIME: options.get(CONF_DAILY_MEALPLAN_SYNC_TIME)
            or data.get(CONF_DAILY_MEALPLAN_SYNC_TIME)
            or "07:00",
            CONF_MEALPLAN_SYNC_MODE: options.get(CONF_MEALPLAN_SYNC_MODE)
            or data.get(CONF_MEALPLAN_SYNC_MODE)
            or MEALPLAN_SYNC_MODE_DAILY,
            CONF_MEALPLAN_SYNC_WEEKDAY: options.get(CONF_MEALPLAN_SYNC_WEEKDAY)
            or data.get(CONF_MEALPLAN_SYNC_WEEKDAY)
            or "sunday",
            CONF_MEALPLAN_SYNC_DAYS_AHEAD: _coerce_int(
                options.get(
                    CONF_MEALPLAN_SYNC_DAYS_AHEAD,
                    data.get(CONF_MEALPLAN_SYNC_DAYS_AHEAD, 7),
                ),
                7,
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(values),
        )

    def _build_options_schema(self, values: dict):
        """Build the options schema with optional todo selector."""
        todo_options = {
            entity: entity for entity in self.hass.states.async_entity_ids("todo")
        }
        return vol.Schema(_build_schema_fields(values, todo_options))

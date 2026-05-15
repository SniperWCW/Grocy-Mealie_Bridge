"""Config flow for Mealie Grocy Bridge integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_EXCLUDED_FOODS,
)

class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mealie Grocy Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="Mealie Grocy Bridge", 
                data=user_input
            )

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_MEALIE_URL, default="http://10.11.12.200:9000"): str,
                vol.Required(CONF_MEALIE_TOKEN): str,
                vol.Required(CONF_GROCY_URL, default="http://10.11.12.172:9283"): str,
                vol.Required(CONF_GROCY_TOKEN): str,
                vol.Optional(CONF_EXCLUDED_FOODS, default="salz, pfeffer, wasser, öl, zucker, mehl, gewürz, kümmel, sasilikum, cayennepfeffer, chilli, curry, honig, koriander, kurkuma, majoran, meersalz, muskat, oregano, paprikapulver, petersilie, schnittlauch, thymian"): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return MealieGrocyBridgeOptionsFlowHandler(config_entry)


class MealieGrocyBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mealie Grocy Bridge."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Wir schlucken das config_entry hier im Konstruktor,
        # rufen aber die Basisklasse absolut leer auf.
        super().__init__()

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # self.config_entry wird von Home Assistant Core danach automatisch gesetzt
        options = self.config_entry.options
        data = self.config_entry.data

        current_mealie_url = options.get(CONF_MEALIE_URL) or data.get(CONF_MEALIE_URL) or ""
        current_mealie_token = options.get(CONF_MEALIE_TOKEN) or data.get(CONF_MEALIE_TOKEN) or ""
        current_grocy_url = options.get(CONF_GROCY_URL) or data.get(CONF_GROCY_URL) or ""
        current_grocy_token = options.get(CONF_GROCY_TOKEN) or data.get(CONF_GROCY_TOKEN) or ""
        current_exclusions = options.get(CONF_EXCLUDED_FOODS) or data.get(CONF_EXCLUDED_FOODS) or "Wasser, Salz, Pfeffer"

        OPTIONS_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_MEALIE_URL, default=current_mealie_url): str,
                vol.Required(CONF_MEALIE_TOKEN, default=current_mealie_token): str,
                vol.Required(CONF_GROCY_URL, default=current_grocy_url): str,
                vol.Required(CONF_GROCY_TOKEN, default=current_grocy_token): str,
                vol.Optional(CONF_EXCLUDED_FOODS, default=current_exclusions): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)

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
)

class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mealie Grocy Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Hier könnte man später eine Validierung der URLs einbauen
            return self.async_create_entry(
                title="Mealie Grocy Bridge", 
                data=user_input
            )

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_MEALIE_URL): str,
                vol.Required(CONF_MEALIE_TOKEN): str,
                vol.Required(CONF_GROCY_URL): str,
                vol.Required(CONF_GROCY_TOKEN): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

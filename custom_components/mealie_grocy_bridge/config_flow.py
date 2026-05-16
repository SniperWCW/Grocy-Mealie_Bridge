"""Config flow for Mealie Grocy Bridge integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

# Hier importieren wir die Konfigurations-Keys (Strings) aus deiner const.py
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_EXCLUDED_FOODS,
    CONF_TODO_ENTITY,  # NEU: Der Key für die To-Do-Listen-Entität ("todo_entity")
)

class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mealie Grocy Bridge."""

    # Version des Konfigurations-Flows (wichtig bei zukünftigen Schema-Updates)
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step (wird beim ersten Hinzufügen der Integration aufgerufen)."""
        errors = {}

        # Wenn der Nutzer das Formular abgeschickt hat (user_input ist nicht leer)
        if user_input is not None:
            return self.async_create_entry(
                title="Mealie Grocy Bridge", 
                data=user_input
            )

        # NEU: Vorhandene To-Do-Listen aus HA laden, damit wir auch beim Ersteirichten das Feld füllen können
        todo_entities = self.hass.states.async_entity_ids("todo")
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Das Formular-Schema für die Ersteinrichtung der Integration
        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_MEALIE_URL, default="http://10.11.12.200:9000"): str,
                vol.Required(CONF_MEALIE_TOKEN): str,
                vol.Required(CONF_GROCY_URL, default="http://10.11.12.172:9283"): str,
                vol.Required(CONF_GROCY_TOKEN): str,
                vol.Optional(CONF_EXCLUDED_FOODS, default="salz, pfeffer, wasser, öl, zucker, mehl, gewürz, kümmel, sasilikum, cayennepfeffer, chilli, curry, honig, koriander, kurkuma, majoran, meersalz, muskat, oregano, paprikapulver, petersilie, schnittlauch, thymian"): str,
                # NEU: Dropdown für To-Do-Listen bei der Ersteinrichtung (optional, falls keine Listen existieren)
                vol.Optional(CONF_TODO_ENTITY): vol.In(todo_options),
            }
        )

        # Zeigt das Ersteinrichtungs-Formular in der HA-Oberfläche an
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Verknüpft den Konfigurations-Flow mit dem Options-Flow (für das 'Konfigurieren'-Menü)."""
        return MealieGrocyBridgeOptionsFlowHandler(config_entry)


class MealieGrocyBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mealie Grocy Bridge (Das Menü, wenn man auf 'Konfigurieren' klickt)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Ruft den Konstruktor der Home Assistant Basisklasse auf
        super().__init__()

    async def async_step_init(self, user_input=None):
        """Manage the options (Wird geladen, sobald das Optionen-Fenster öffnet)."""
        
        # Wenn der Nutzer im "Konfigurieren"-Menü auf Speichern drückt
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Bereits gespeicherte Optionen und Ersteinrichtungsdaten abrufen
        options = self.config_entry.options
        data = self.config_entry.data

        # Aktuell eingetragene Werte auslesen, damit sie im Formular vorausgefüllt sind
        current_mealie_url = options.get(CONF_MEALIE_URL) or data.get(CONF_MEALIE_URL) or ""
        current_mealie_token = options.get(CONF_MEALIE_TOKEN) or data.get(CONF_MEALIE_TOKEN) or ""
        current_grocy_url = options.get(CONF_GROCY_URL) or data.get(CONF_GROCY_URL) or ""
        current_grocy_token = options.get(CONF_GROCY_TOKEN) or data.get(CONF_GROCY_TOKEN) or ""
        current_exclusions = options.get(CONF_EXCLUDED_FOODS) or data.get(CONF_EXCLUDED_FOODS) or "Wasser, Salz, Pfeffer"
        
        # NEU: Holt die aktuell ausgewählte To-Do-Liste aus den Optionen oder Daten
        current_todo = options.get(CONF_TODO_ENTITY) or data.get(CONF_TODO_ENTITY) or ""

        # NEU: Holt live alle im Home Assistant registrierten Entitäten aus der Domäne "todo" (z.B. ['todo.bring_einkaufsliste'])
        todo_entities = self.hass.states.async_entity_ids("todo")
        
        # NEU: Erstellt das Dictionary für das Dropdown-Menü im Format {"todo.entity_id": "todo.entity_id"}
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Das Formular-Schema für das "Konfigurieren"-Menü definieren
        OPTIONS_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_MEALIE_URL, default=current_mealie_url): str,
                vol.Required(CONF_MEALIE_TOKEN, default=current_mealie_token): str,
                vol.Required(CONF_GROCY_URL, default=current_grocy_url): str,
                vol.Required(CONF_GROCY_TOKEN, default=current_grocy_token): str,
                vol.Optional(CONF_EXCLUDED_FOODS, default=current_exclusions): str,
                # NEU: Das Dropdown-Auswahlfeld für die To-Do-Liste im Konfigurations-Menü
                vol.Optional(CONF_TODO_ENTITY, default=current_todo): vol.In(todo_options),
            }
        )

        # Zeigt das Konfigurations-Formular in der UI an
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)

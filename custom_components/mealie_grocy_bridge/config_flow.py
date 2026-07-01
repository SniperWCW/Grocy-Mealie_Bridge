"""Config flow for Mealie Grocy Bridge integration.

Diese Datei steuert den Einrichtungs-Prozess (Config Flow) in der Benutzeroberfläche
sowie das spätere Ändern von Einstellungen über die Schaltfläche "Konfigurieren" (Options Flow).
"""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

# Import der zentralen Konfigurationsschlüssel aus der const.py
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_EXCLUDED_FOODS,
    CONF_TODO_ENTITY,
    CONF_DAILY_MEALPLAN_SYNC_ENABLED,
    CONF_DAILY_MEALPLAN_SYNC_TIME,
)

TIME_VALIDATOR = vol.Match(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Klasse zur Handhabung der Ersteinrichtung der Integration."""

    # Version des Konfigurations-Flows. Wichtig, falls sich Eingabefelder in der Zukunft ändern
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Wird aufgerufen, wenn der Nutzer die Integration neu hinzufügen möchte."""
        errors = {}

        # Wenn der Nutzer das Formular ausgefüllt und auf 'Absenden' geklickt hat
        if user_input is not None:
            return self.async_create_entry(
                title="Mealie Grocy Bridge", 
                data=user_input
            )

        # Alle aktuell in Home Assistant registrierten To-Do-Entitäten auslesen
        todo_entities = self.hass.states.async_entity_ids("todo")
        
        # Erstellt ein Dictionary im Format {"todo.einkaufsliste": "todo.einkaufsliste"} für das Dropdown-Menü
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Das Eingabe-Formular für die Ersteinrichtung definieren
        DATA_SCHEMA = vol.Schema(
            {
                # Mealie Verbindungsdaten (Vorausgefüllt mit deiner Docker/LXC IP)
                vol.Required(CONF_MEALIE_URL, default="http://10.11.12.200:9000"): str,
                vol.Required(CONF_MEALIE_TOKEN): str,
                
                # Grocy Verbindungsdaten (Vorausgefüllt mit deiner VM IP)
                vol.Required(CONF_GROCY_URL, default="http://10.11.12.172:9283"): str,
                vol.Required(CONF_GROCY_TOKEN): str,
                
                # Standard-Ausschlussliste für die Filterung (Grundnahrungsmittel)
                vol.Optional(
                    CONF_EXCLUDED_FOODS, 
                    default="salz, pfeffer, wasser, öl, zucker, mehl, gewürz, kümmel, basilikum, cayennepfeffer, chilli, curry, honig, koriander, kurkuma, majoran, meersalz, muskat, oregano, paprikapulver, petersilie, schnittlauch, thymian"
                ): str,
                
                # Dropdown-Auswahlfeld für die gewünschte To-Do-Liste
                vol.Optional(CONF_TODO_ENTITY): vol.In(todo_options),
                vol.Optional(CONF_DAILY_MEALPLAN_SYNC_ENABLED, default=False): bool,
                vol.Optional(CONF_DAILY_MEALPLAN_SYNC_TIME, default="07:00"): TIME_VALIDATOR,
            }
        )

        # Zeigt das leere oder fehlerhafte Formular in der Home Assistant UI an
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Verknüpft diesen Config-Flow mit dem unten stehenden Options-Flow (Konfigurieren-Button)."""
        return MealieGrocyBridgeOptionsFlowHandler(config_entry)


class MealieGrocyBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Klasse zur Handhabung von nachträglichen Einstellungsänderungen."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialisiert den Options-Flow Handler."""
        super().__init__()
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Verwaltet das Formular, wenn der Nutzer auf 'Konfigurieren' klickt."""
        # Wenn der Nutzer die Änderungen im Optionen-Formular speichert
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Bestehende Konfigurationen auslesen, um sie als Standardwerte im Formular vorzubelegen
        options = self.config_entry.options
        data = self.config_entry.data

        # Prüft zuerst in den Optionen (geänderte Werte) und fällt andernfalls auf die Erstkonfiguration zurück
        current_mealie_url = options.get(CONF_MEALIE_URL) or data.get(CONF_MEALIE_URL) or ""
        current_mealie_token = options.get(CONF_MEALIE_TOKEN) or data.get(CONF_MEALIE_TOKEN) or ""
        current_grocy_url = options.get(CONF_GROCY_URL) or data.get(CONF_GROCY_URL) or ""
        current_grocy_token = options.get(CONF_GROCY_TOKEN) or data.get(CONF_GROCY_TOKEN) or ""
        current_exclusions = options.get(CONF_EXCLUDED_FOODS) or data.get(CONF_EXCLUDED_FOODS) or ""
        current_todo = options.get(CONF_TODO_ENTITY) or data.get(CONF_TODO_ENTITY) or ""
        current_daily_sync_enabled = options.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED)
        if current_daily_sync_enabled is None:
            current_daily_sync_enabled = data.get(CONF_DAILY_MEALPLAN_SYNC_ENABLED, False)
        current_daily_sync_time = options.get(CONF_DAILY_MEALPLAN_SYNC_TIME) or data.get(CONF_DAILY_MEALPLAN_SYNC_TIME) or "07:00"

        # Erneut alle aktuellen To-Do-Listen aus HA laden (falls in der Zwischenzeit neue Listen dazukamen)
        todo_entities = self.hass.states.async_entity_ids("todo")
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Das Formular-Schema für das "Konfigurieren"-Menü aufbauen (vorausgefüllt mit aktuellen Werten)
        schema_fields = {
            vol.Required(CONF_MEALIE_URL, default=current_mealie_url): str,
            vol.Required(CONF_MEALIE_TOKEN, default=current_mealie_token): str,
            vol.Required(CONF_GROCY_URL, default=current_grocy_url): str,
            vol.Required(CONF_GROCY_TOKEN, default=current_grocy_token): str,
            vol.Optional(CONF_EXCLUDED_FOODS, default=current_exclusions): str,
            vol.Optional(CONF_DAILY_MEALPLAN_SYNC_ENABLED, default=current_daily_sync_enabled): bool,
            vol.Optional(CONF_DAILY_MEALPLAN_SYNC_TIME, default=current_daily_sync_time): TIME_VALIDATOR,
        }

        if todo_options:
            todo_default = current_todo if current_todo in todo_options else next(iter(todo_options))
            schema_fields[vol.Optional(CONF_TODO_ENTITY, default=todo_default)] = vol.In(todo_options)
        else:
            schema_fields[vol.Optional(CONF_TODO_ENTITY, default=current_todo)] = str

        OPTIONS_SCHEMA = vol.Schema(schema_fields)

        # Formular mit den vorbelegten Werten anzeigen
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)

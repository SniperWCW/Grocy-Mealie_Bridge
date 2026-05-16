"""Config flow for Mealie Grocy Bridge integration."""
# Voluptuous wird für die Validierung und Strukturierung der Eingabemasken (Formulare) genutzt
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

# Importiert die zentralen Konstanten (technische Keys), damit Tippfehler ausgeschlossen sind
from .const import (
    DOMAIN,
    CONF_MEALIE_URL,
    CONF_MEALIE_TOKEN,
    CONF_GROCY_URL,
    CONF_GROCY_TOKEN,
    CONF_EXCLUDED_FOODS,
    CONF_TODO_ENTITY,  # Technischer Key für das Feld der To-Do-Liste ("todo_entity")
)

class MealieGrocyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mealie Grocy Bridge."""

    # Die Schema-Version. Erleichtert spätere Migrationen, falls sich Datenstrukturen ändern
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step (wird beim ersten Hinzufügen der Integration aufgerufen)."""
        # Leeres Dictionary für eventuelle Validierungsfehler (z.B. "Verbindung fehlgeschlagen")
        errors = {}

        # user_input ist gefüllt, sobald der Nutzer im ersten Formular auf "Absenden" drückt
        if user_input is not None:
            # Erstellt den finalen Integrations-Eintrag in Home Assistant mit den eingegebenen Daten
            return self.async_create_entry(
                title="Mealie Grocy Bridge", 
                data=user_input
            )

        # Holt alle registrierten Entitäten aus der Domäne "todo" (z.B. ["todo.einkauf", "todo.stuttgart"])
        todo_entities = self.hass.states.async_entity_ids("todo")
        
        # Erzeugt ein Dictionary für das Dropdown-Menü im Format: {"todo.einkauf": "todo.einkauf"}
        # Falls keine Listen existieren, bleibt das Dictionary leer ({})
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Definition der Eingabefelder für die allererste Einrichtung
        DATA_SCHEMA = vol.Schema(
            {
                # vol.Required = Pflichtfeld. default = Vorausgefüllter Wert in der UI
                vol.Required(CONF_MEALIE_URL, default="http://10.11.12.200:9000"): str,
                vol.Required(CONF_MEALIE_TOKEN): str,
                vol.Required(CONF_GROCY_URL, default="http://10.11.12.172:9283"): str,
                vol.Required(CONF_GROCY_TOKEN): str,
                # vol.Optional = Kann leer gelassen werden. Nimmt standardmäßig deine Gewürzliste
                vol.Optional(CONF_EXCLUDED_FOODS, default="salz, pfeffer, wasser, öl, zucker, mehl, gewürz, kümmel, sasilikum, cayennepfeffer, chilli, curry, honig, koriander, kurkuma, majoran, meersalz, muskat, oregano, paprikapulver, petersilie, schnittlauch, thymian"): str,
                # vol.In(todo_options) zwingt die UI, ein Dropdown mit den gefundenen Listen anzuzeigen
                vol.Optional(CONF_TODO_ENTITY): vol.In(todo_options),
            }
        )

        # Zeigt das visuelle Formular im Browser an (step_id entspricht dem Methodennamen nach "async_step_")
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Verknüpft den Konfigurations-Flow mit dem Options-Flow (für das 'Konfigurieren'-Menü)."""
        # Übergibt die bestehende Konfiguration an den Options-Handler unten
        return MealieGrocyBridgeOptionsFlowHandler(config_entry)


class MealieGrocyBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mealie Grocy Bridge (Das Menü, wenn man auf 'Konfigurieren' klickt)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Initialisiert die Basisklasse von Home Assistant ohne zusätzliche Argumente
        super().__init__()

    async def async_step_init(self, user_input=None):
        """Manage the options (Wird geladen, sobald das Optionen-Fenster öffnet)."""
        
        # Wird ausgeführt, wenn der Nutzer im "Konfigurieren"-Menü auf "Speichern" klickt
        if user_input is not None:
            # Schreibt die neuen Werte in die Optionen der Integration (löst ein Update-Event aus)
            return self.async_create_entry(title="", data=user_input)

        # Holt die aktuell im System hinterlegten Werte aus den Optionen oder der Ersteinrichtung
        options = self.config_entry.options
        data = self.config_entry.data

        # Priorität beim Vorausfüllen: 1. Laufende Optionen, 2. Ersteinrichtungsdaten, 3. Leerer String
        # Das verhindert, dass Felder leer werden, wenn man das Menü zum ersten Mal öffnet
        current_mealie_url = options.get(CONF_MEALIE_URL) or data.get(CONF_MEALIE_URL) or ""
        current_mealie_token = options.get(CONF_MEALIE_TOKEN) or data.get(CONF_MEALIE_TOKEN) or ""
        current_grocy_url = options.get(CONF_GROCY_URL) or data.get(CONF_GROCY_URL) or ""
        current_grocy_token = options.get(CONF_GROCY_TOKEN) or data.get(CONF_GROCY_TOKEN) or ""
        current_exclusions = options.get(CONF_EXCLUDED_FOODS) or data.get(CONF_EXCLUDED_FOODS) or "Wasser, Salz, Pfeffer"
        
        # Liest die aktuell gewählte To-Do-Liste aus (falls schon mal gespeichert)
        current_todo = options.get(CONF_TODO_ENTITY) or data.get(CONF_TODO_ENTITY) or ""

        # Sucht live im HA-System nach allen aktuell existierenden To-Do-Entitäten
        todo_entities = self.hass.states.async_entity_ids("todo")
        
        # Erstellt wieder das Dictionary für das Dropdown-Menü
        todo_options = {entity: entity for entity in todo_entities} if todo_entities else {}

        # Baut das Formular-Schema für das Optionen-Menü auf
        OPTIONS_SCHEMA = vol.Schema(
            {
                # Die Eingabemasken werden mit den ermittelten "current_"-Werten vorausgefüllt
                vol.Required(CONF_MEALIE_URL, default=current_mealie_url): str,
                vol.Required(CONF_MEALIE_TOKEN, default=current_mealie_token): str,
                vol.Required(CONF_GROCY_URL, default=current_grocy_url): str,
                vol.Required(CONF_GROCY_TOKEN, default=current_grocy_token): str,
                vol.Optional(CONF_EXCLUDED_FOODS, default=current_exclusions): str,
                # Das Dropdown-Feld für die To-Do-Liste im Optionen-Menü
                vol.Optional(CONF_TODO_ENTITY, default=current_todo): vol.In(todo_options),
            }
        )

        # Rendert das Konfigurationsfenster mit dem definierten Schema im Frontend
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)

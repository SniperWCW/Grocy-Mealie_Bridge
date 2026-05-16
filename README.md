# Mealie-Grocy Bridge Integration für Home Assistant

Diese maßgeschneiderte Home Assistant Integration schließt die Lücke zwischen deiner Rezeptverwaltung (**Mealie**) und deiner Vorratsdatenbank (**Grocy**). Sie analysiert vollautomatisch im Hintergrund, welche Zutaten deiner Rezepte bereits im Haus sind, berechnet einen intelligenten Match-Score und erlaubt es dir, Mahlzeiten direkt zu planen oder fehlende Zutaten mit einem Klick auf deine Einkaufsliste zu setzen.

---

## 🚀 Features & Kernfunktionen

- **Automatischer API-Abgleich:** Vergleicht im Hintergrund Mealie-Rezeptzutaten direkt mit dem aktuellen Grocy-Warenbestand.
- **Intelligenter Match-Score mit MHD-Logik:** Berechnet prozentual, wie gut ein Rezept zu deinen vorhandenen Vorräten passt. Zutaten, die in Kürze ablaufen (innerhalb der nächsten 30 Tage) oder bereits abgelaufen sind, verleihen dem Rezept automatisch einen **Score-Bonus von +15 %**, um Lebensmittelverschwendung aktiv zu verhindern.
- **MHD-Warnindikator:** Rezepte mit kritischen Mindesthaltbarkeitsdaten erhalten ein Kennzeichen (`hasExpiring`), um im Frontend optisch markiert werden zu können.
- **8-Tage-Speiseplan-Filter:** Rezepte, die bereits für die nächsten 8 Tage im Mealie-Speiseplan eingetragen sind, werden automatisch aus den Vorschlägen ausgeblendet.
- **Dynamische Ausschlussliste:** Standardzutaten und Gewürze (z.B. Salz, Pfeffer, Wasser, Öl) können direkt über die Integrations-Optionen ignoriert werden, um den Match-Score nicht zu verfälschen.

### ✨ Neu ab v0.1.4
- **Native Home Assistant Dienste:** Keine manuellen Jinja2-Skripte, Hilfskonstrukte oder Automatisierungen mehr nötig. Die gesamte Logik läuft performant direkt im Python-Kern der Integration.
- **Automatischer Sofort-Refresh:** Sobald ein Rezept über den integrierten Dienst auf den Speiseplan gesetzt wird, triggert die Bridge ein sofortiges Update des Sensors. Das geplante Gericht verschwindet ohne Verzögerung aus den Vorschlägen.
- **Ultra-intelligentes Teilwort-Matching (Sub-String):** Erkennt jetzt auch Grocy-Produkte anhand von Rezept-Teilwörtern (z. B. Mealie: `"Mehl"` ➔ Grocy: `"Weizenmehl Typ 405"`). Aktiv ab 4 Buchstaben, um Fehltreffer zu vermeiden.
- **Mengen-Isolierung:** Zahlenfragmente und Mengenangaben im Rezepttext werden beim Abgleich vorab herausgefiltert, um saubere String-Vergleiche zu garantieren.

---

## 🛠️ Registrierte Dienste (Services)

Die Integration stellt nach der Installation zwei native Dienste zur Verfügung. Diese arbeiten ultraschnell direkt mit dem internen **Rezept-Index** des Sensors (wobei `0` für das erste Rezept im Sensor steht, `1` für das zweite, etc.).

### 1. `mealie_grocy_bridge.set_to_next_free_day`
Nimmt das Rezept am angegebenen Index, sucht vollautomatisch den nächsten freien Tag (Typ: Abendessen/Dinner) im Mealie-Speiseplan der kommenden 30 Tage und bucht es dort ein. 
*Zusätzlich wird eine native Home Assistant Push-Benachrichtigung mit dem Namen des Gerichts und dem gewählten Datum versendet.*

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*: Die Position des Rezepts im Sensor (z. B. `0`).

### 2. `mealie_grocy_bridge.add_missing_ingredients`
Liest das Attribut `missingIngredients` des ausgewählten Rezept-Index aus und fügt jede fehlende Zutat einzeln als To-Do-Punkt zu deiner Einkaufsliste (`todo.stuttgart`) hinzu.

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*: Die Position des Rezepts im Sensor (z. B. `0`).

---

## 🏗️ Systemarchitektur Backend

Die Integration basiert auf einer zentralen, schlanken Systemarchitektur:

### Der Sensor (`sensor.mealie_grocy_kochvorschlage`)
Der Sensor läuft über einen `DataUpdateCoordinator` und fragt standardmäßig alle **30 Minuten** die APIs von Mealie und Grocy ab. Er stellt die berechneten Daten in folgenden Attributen bereit:
- `recipes`: Ein strukturiertes JSON-Array mit den Rohdaten der Top-Rezepte (`recipeId`, `recipeName`, `matchScore`, `matchingIngredients`, `missingIngredients`, `url`, `hasExpiring`).
- `markdown_suggestions`: Ein Textblock zur einfachen Darstellung.

---

## 📺 Frontend-Beispiele (Lovelace Dashboard)

Für die Darstellung auf dem Dashboard steht ein Design zur Verfügung, welches die `custom:expander-card` nutzt, um im Dashboard massiv Platz zu sparen und die Vorschläge kompakt anzuordnen.

```yaml
type: custom:expander-card
title: Rezeptvorschläge V2
cards:
  - type: grid
    columns: 2
    square: false
    cards:
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
              'recipes') %} {% if recipes and recipes|length > 0 %}
                ### 🍳 {{ recipes[0].recipeName | upper }} {% if recipes[0].hasExpiring | default(false) %}🔥{% endif %}
                📊 Score: **{{ recipes[0].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[0].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[0].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[0].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: action
                icon: mdi:cart-plus
                icon_color: primary
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.add_missing_ingredients
                  data:
                    recipe_index: 0
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.set_to_next_free_day
                  data:
                    recipe_index: 0
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
              'recipes') %} {% if recipes and recipes|length > 1 %}
                ### 🍳 {{ recipes[1].recipeName | upper }} {% if recipes[1].hasExpiring | default(false) %}🔥{% endif %}
                📊 Score: **{{ recipes[1].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[1].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[1].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[1].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: action
                icon: mdi:cart-plus
                icon_color: primary
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.add_missing_ingredients
                  data:
                    recipe_index: 1
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.set_to_next_free_day
                  data:
                    recipe_index: 1
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
              'recipes') %} {% if recipes and recipes|length > 2 %}
                ### 🍳 {{ recipes[2].recipeName | upper }} {% if recipes[2].hasExpiring | default(false) %}🔥{% endif %}
                📊 Score: **{{ recipes[2].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[2].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[2].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[2].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: action
                icon: mdi:cart-plus
                icon_color: primary
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.add_missing_ingredients
                  data:
                    recipe_index: 2
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.set_to_next_free_day
                  data:
                    recipe_index: 2
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
              'recipes') %} {% if recipes and recipes|length > 3 %}
                ### 🍳 {{ recipes[3].recipeName | upper }} {% if recipes[3].hasExpiring | default(false) %}🔥{% endif %}
                📊 Score: **{{ recipes[3].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[3].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[3].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[3].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: action
                icon: mdi:cart-plus
                icon_color: primary
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.add_missing_ingredients
                  data:
                    recipe_index: 3
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: mealie_grocy_bridge.set_to_next_free_day
                  data:
                    recipe_index: 3
    grid_options:
      columns: 24
      rows: auto
grid_options:
  columns: 24
  rows: auto

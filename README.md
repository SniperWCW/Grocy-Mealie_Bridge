# Mealie-Grocy Bridge Integration für Home Assistant

Diese maßgeschneiderte Home Assistant Integration schließt die Lücke zwischen deiner Rezeptverwaltung (**Mealie**) und deiner Vorratsdatenbank (**Grocy**). Sie analysiert vollautomatisch im Hintergrund, welche Zutaten deiner Rezepte bereits im Haus sind, berechnet einen Match-Score und ermöglicht es dir, fehlende Zutaten mit einem einzigen Klick direkt auf deine Home Assistant To-Do-Liste zu setzen.

## 🚀 Features

- **Automatischer Abgleich:** Vergleicht Mealie-Rezeptzutaten mit dem aktuellen Grocy-Warenbestand.
- **Intelligenter Match-Score mit MHD-Logik:** Berechnet prozentual, wie gut ein Rezept zu deinen aktuellen Vorräten passt. Zutaten, die in Kürze ablaufen (innerhalb der nächsten 30 Tage) oder bereits abgelaufen sind, verleihen dem Rezept automatisch einen **Score-Bonus von +15 %**, um Lebensmittelverschwendung aktiv zu verhindern.
- **MHD-Warnindikator:** Rezepte mit kritischen Mindesthaltbarkeitsdaten werden direkt im Frontend optisch markiert.
- **Grundzutaten-Filter:** Ignoriert Standardzutaten wie Salz, Pfeffer, Wasser oder Öl, um den Score nicht zu verfälschen.
- **Direkte Einkaufslisten-Anbindung:** Fehlende Zutaten werden über ein Home Assistant Skript direkt in die Einkaufsliste (`todo.stuttgart`) übertragen.
- **Keine Drittanbieter-Tools:** Ersetzt komplexe externe n8n-Workflows vollständig durch native Home Assistant Services.

---

## 🛠️ Systemarchitektur Backend

Die Integration besteht aus drei zentralen Backend-Komponenten:

### 1. Der Sensor (`sensor.mealie_grocy_kochvorschlage`)
Der Sensor läuft über einen `DataUpdateCoordinator` und fragt standardmäßig alle **30 Minuten** die APIs von Mealie und Grocy ab. Er stellt die berechneten Daten in zwei Attributen bereit:
- `recipes`: Ein strukturiertes JSON-Array mit den Rohdaten der Top-Rezepte (Name, Score, vorhandene & fehlende Zutaten, URL, MHD-Status).
- `markdown_suggestions`: Ein fertig formatierter Textblock für die einfache Anzeige im Dashboard.

### 2. Das Automatisierungs-Skript (`script.zutaten_auf_to_do_liste_setzen`)
Dieses Skript wird vom Dashboard aufgerufen, nimmt den Index des ausgewählten Rezepts entgegen und pusht alle fehlenden Zutaten in einer Schleife auf die To-Do-Liste.

Füge dieses Skript in deine `scripts.yaml` ein:

```yaml
zutaten_auf_to_do_liste_setzen:
  alias: "Zutaten auf To-Do-Liste setzen"
  mode: parallel
  fields:
    recipe_index:
      description: "Der Index des Rezepts (0 für das 1. Rezept, 1 für das 2. Rezept...)"
      example: 0
  sequence:
    - variables:
        missing_ingredients: >-
          {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage', 'recipes') %}
          {% if recipes and recipes[recipe_index] is defined %}
            {{ recipes[recipe_index].missingIngredients }}
          {% else %}
            {{ [] }}
          {% endif %}
    - condition: template
      value_template: "{{ missing_ingredients | length > 0 }}"
    - repeat:
        for_each: "{{ missing_ingredients }}"
        sequence:
          - action: todo.add_item
            data:
              item: "{{ repeat.item }}"
            target:
              entity_id: todo.stuttgart
```
Frontend Beispiele (Lovelace Dashboard)
Für die Darstellung auf dem Dashboard stehen zwei verschiedene Design-Varianten zur Verfügung, die beide die custom:expander-card nutzen, um im Dashboard Platz zu sparen.

Variante 1: Klassische Listenansicht (Kompakt)
Diese Variante nutzt das vom Sensor vorformatierte Text-Attribut. Die Buttons zum Hinzufügen der Einkaufsliste sind kompakt als Liste darunter angeordnet.

```YAML
type: custom:expander-card
title: Expander Card
cards:
  - square: false
    type: grid
    columns: 1
    cards:
      - type: markdown
        title: 👨‍🍳 Menü-Vorschläge
        content: >-
          {{ state_attr('sensor.mealie_grocy_kochvorschlage', 'markdown_suggestions') }}
      - type: entities
        title: Zutaten direkt übertragen
        show_header_toggle: false
        entities:
          - type: button
            name: Zutaten vom 1. Rezept
            icon: mdi:cart-plus
            action_name: Hinzufügen
            tap_action:
              action: perform-action
              perform_action: script.zutaten_auf_to_do_liste_setzen
              data:
                recipe_index: 0
              target: {}
          - type: button
            name: Zutaten vom 2. Rezept
            icon: mdi:cart-plus
            action_name: Hinzufügen
            tap_action:
              action: perform-action
              perform_action: script.zutaten_auf_to_do_liste_setzen
              data:
                recipe_index: 1
              target: {}
          - type: button
            name: Zutaten vom 3. Rezept
            icon: mdi:cart-plus
            action_name: Hinzufügen
            tap_action:
              action: perform-action
              perform_action: script.zutaten_auf_to_do_liste_setzen
              data:
                recipe_index: 2
              target: {}
````
Variante 2: Modernes 2x2 Kachel-Raster
Diese fortgeschrittene Variante greift direkt auf die Rohdaten zu und rendert die Top 4 Rezepte in einem voll-dynamischen, quadratischen Layout. Text, Rezept-Link und Einkaufslisten-Button bilden hier pro Rezept eine feste visuelle Einheit.

````YAML
type: custom:expander-card
title: Rezeptvorschläge
cards:
  - type: grid
    columns: 2
    square: false
    cards:
      # REZEPT 1
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage', 'recipes') %}  
              {% if recipes and recipes|length > 0 %}
                ### 🍳 {{ recipes[0].recipeName | upper }} {% if recipes[0].hasExpiring | default(false) %}🔥 MHD!{% endif %}
                📊 Score: **{{ recipes[0].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[0].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[0].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[0].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            chips:
              - type: action
                icon: mdi:cart-plus
                tap_action:
                  action: perform-action
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 0
                  target: {}
                icon_color: primary
            alignment: center

      # REZEPT 2
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage', 'recipes') %} 
              {% if recipes and recipes|length > 1 %}
                ### 🍳 {{ recipes[1].recipeName | upper }} {% if recipes[1].hasExpiring | default(false) %}🔥 MHD!{% endif %}
                📊 Score: **{{ recipes[1].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[1].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[1].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[1].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            chips:
              - type: action
                icon: mdi:cart-plus
                tap_action:
                  action: perform-action
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 1
                  target: {}
                icon_color: primary
            alignment: center

      # REZEPT 3
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage', 'recipes') %} 
              {% if recipes and recipes|length > 2 %}
                ### 🍳 {{ recipes[2].recipeName | upper }} {% if recipes[2].hasExpiring | default(false) %}🔥 MHD!{% endif %}
                📊 Score: **{{ recipes[2].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[2].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[2].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[2].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            chips:
              - type: action
                icon: mdi:cart-plus
                tap_action:
                  action: perform-action
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 2
                  target: {}
                icon_color: primary
            alignment: center

      # REZEPT 4
      - type: vertical-stack
        cards:
          - type: markdown
            content: >-
              {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage', 'recipes') %} 
              {% if recipes and recipes|length > 3 %}
                ### 🍳 {{ recipes[3].recipeName | upper }} {% if recipes[3].hasExpiring | default(false) %}🔥 MHD!{% endif %}
                📊 Score: **{{ recipes[3].matchScore }}%**
                ✅ Vorhanden: `{% for ing in recipes[3].matchingIngredients %}{{ ing | capitalize }}{{ ", " if not loop.last }}{% endfor %}`
                🛒 Einkaufen: *{{ recipes[3].missingIngredients | join(', ') }}*
                
                🔗 **[👉 REZEPT IN MEALIE ÖFFNEN]({{ recipes[3].url }})**
              {% else %}
                ### 🍳 Kein Rezept gefunden
              {% endif %}
          - type: custom:mushroom-chips-card
            chips:
              - type: action
                icon: mdi:cart-plus
                tap_action:
                  action: perform-action
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 3
                  target: {}
                icon_color: primary
            alignment: center
    grid_options:
      columns: 24
      rows: auto
grid_options:
  columns: 24
  rows: auto

````
⚙️ Voraussetzungen Frontend
Für eine fehlerfreie und optisch ansprechende Darstellung im Dashboard werden folgende HACS Frontend-Erweiterungen zwingend benötigt:

custom:expander-card (Zur einklappbaren und platzsparenden Strukturierung des Dashboards)

custom:mushroom (Für die kompakte mushroom-chips-card Steuerung der Einkaufsliste)

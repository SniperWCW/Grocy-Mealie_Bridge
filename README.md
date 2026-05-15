# Mealie-Grocy Bridge Integration für Home Assistant

Diese maßgeschneiderte Home Assistant Integration schließt die Lücke zwischen deiner Rezeptverwaltung (**Mealie**) und deiner Vorratsdatenbank (**Grocy**). Sie analysiert vollautomatisch im Hintergrund, welche Zutaten deiner Rezepte bereits im Haus sind, berechnet einen Match-Score und ermöglicht es dir, fehlende Zutaten mit einem einzigen Klick direkt auf deine Home Assistant To-Do-Liste zu setzen.

## 🚀 Features

- **Automatischer Abgleich:** Vergleicht Mealie-Rezeptzutaten mit dem aktuellen Grocy-Warenbestand.
- **Intelligenter Match-Score mit MHD-Logik:** Berechnet prozentual, wie gut ein Rezept zu deinen aktuellen Vorräten passt. Zutaten, die in Kürze ablaufen (innerhalb der nächsten 30 Tage) oder bereits abgelaufen sind, verleihen dem Rezept automatisch einen **Score-Bonus von +15 %**, um Lebensmittelverschwendung aktiv zu verhindern.
- **MHD-Warnindikator:** Rezepte mit kritischen Mindesthaltbarkeitsdaten werden direkt im Frontend optisch markiert.
- **Grundzutaten-Filter:** Ignoriert Standardzutaten wie Salz, Pfeffer, Wasser oder Öl, um den Score nicht zu verfälschen.
- **Direkte Einkaufslisten-Anbindung:** Fehlende Zutaten werden über ein Home Assistant Skript direkt in die Einkaufsliste (`todo.stuttgart`) übertragen.
- **Keine Drittanbieter-Tools:** Ersetzt komplexe externe n8n-Workflows vollständig durch native Home Assistant Services.
- **Zutaten-Matching:** Gleicht Rezeptzutaten mit dem Grocy-Bestand ab und berechnet einen Match-Score.
- **MHD-Priorisierung:** Rezepte mit Zutaten, die in den nächsten 30 Tagen ablaufen, erhalten einen Bonus von +15% auf den Score.
- **8-Tage-Filter:** Rezepte, die bereits für die nächsten 8 Tage im Mealie-Speiseplan eingetragen sind, werden automatisch aus den Vorschlägen ausgeblendet.
- **Ausschlussliste:** Standardzutaten (Salz, Pfeffer, Wasser etc.) können über die Integrations-Optionen ignoriert werden.

---

## 🛠️ Systemarchitektur Backend

Die Integration besteht aus drei zentralen Backend-Komponenten:

### 1. Der Sensor (`sensor.mealie_grocy_kochvorschlage`)
Der Sensor läuft über einen `DataUpdateCoordinator` und fragt standardmäßig alle **30 Minuten** die APIs von Mealie und Grocy ab. Er stellt die berechneten Daten in zwei Attributen bereit:
- `recipes`: Ein strukturiertes JSON-Array mit den Rohdaten der Top-Rezepte (Name, Score, vorhandene & fehlende Zutaten, URL, MHD-Status).
- `markdown_suggestions`: Ein fertig formatierter Textblock für die einfache Anzeige im Dashboard.

### 2. Das Automatisierungs-Skript (`script.zutaten_auf_to_do_liste_setzen`)
Dieses Skript wird vom Dashboard aufgerufen, nimmt den Index des ausgewählten Rezepts entgegen und pusht alle fehlenden Zutaten in einer Schleife auf die To-Do-Liste.

Es werden zwei Scripts benötigt
1. 
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
```yaml
alias: "Mealie: Rezept auf Speiseplan setzen"
description: >-
  Holt die UUID aus dem Kochvorschläge-Sensor anhand des Index und bucht das
  Gericht auf den nächsten freien Tag. Schickt eine Push-Nachricht als
  Bestätigung.
icon: mdi:calendar-plus
mode: single
fields:
  recipe_index:
    name: Rezept-Index
    description: Die Position des Rezepts im Sensor (0, 1, 2 oder 3)
    required: true
    example: 0
    selector:
      number:
        min: 0
        max: 5
        mode: box
sequence:
  - condition: template
    value_template: >-
      {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
      'recipes') %} {{ recipes is not none and recipes | length > recipe_index
      }}
  - action: mealie_grocy_bridge.set_to_next_free_day
    data:
      recipe_id: >-
        {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
        'recipes') %} {{ recipes[recipe_index].recipeId }}
  - action: notify.notify
    data:
      title: 🍳 Mealie Speiseplan
      message: >-
        {% set recipes = state_attr('sensor.mealie_grocy_kochvorschlage',
        'recipes') %} "{{ recipes[recipe_index].recipeName }}" wurde erfolgreich
        eingetragen!
      data:
        clickAction: /lovelace/speiseplan
````
Frontend Beispiele (Lovelace Dashboard)
Für die Darstellung auf dem Dashboard stehen zwei verschiedene Design-Varianten zur Verfügung, die beide die custom:expander-card nutzen, um im Dashboard Platz zu sparen.

Lovelance Beispiel

```YAML
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
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 0
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: script.mealie_rezept_auf_speiseplan_setzen
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
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 1
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: script.mealie_rezept_auf_speiseplan_setzen
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
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 2
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: script.mealie_rezept_auf_speiseplan_setzen
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
                  perform_action: script.zutaten_auf_to_do_liste_setzen
                  data:
                    recipe_index: 3
              - type: action
                icon: mdi:calendar-plus
                icon_color: info
                tap_action:
                  action: perform-action
                  perform_action: script.mealie_rezept_auf_speiseplan_setzen
                  data:
                    recipe_index: 3
    grid_options:
      columns: 24
      rows: auto
grid_options:
  columns: 24
  rows: auto


````
⚙️ Voraussetzungen Frontend
Für eine fehlerfreie und optisch ansprechende Darstellung im Dashboard werden folgende HACS Frontend-Erweiterungen optional benötigt:

custom:expander-card (Zur einklappbaren und platzsparenden Strukturierung des Dashboards)
custom:mushroom (Für die kompakte mushroom-chips-card Steuerung der Einkaufsliste)


Roadmap/offene Punkte
1. das Rezept soll sobald es die nächsten 8 Tage auf dem Plan steht nicht mehr vorgeschlagen werden. 

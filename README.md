# 🥗 Mealie-Grocy Bridge Integration für Home Assistant

Diese maßgeschneiderte Home Assistant Integration schließt die Lücke zwischen deiner Rezeptverwaltung (**Mealie**) und deiner Vorratsdatenbank (**Grocy**). Sie analysiert vollautomatisch im Hintergrund, welche Zutaten deiner Rezepte bereits im Haus sind, berechnet einen intelligenten Match-Score und erlaubt es dir, Mahlzeiten direkt zu planen oder fehlende Zutaten mit einem Klick auf deine Einkaufsliste zu setzen.

---

## 🚀 Features & Kernfunktionen

- **Automatischer API-Abgleich:** Vergleicht im Hintergrund Mealie-Rezeptzutaten direkt mit dem aktuellen Grocy-Warenbestand.
- **Intelligenter Match-Score mit MHD-Logik:** Berechnet prozentual, wie gut ein Rezept zu deinen vorhandenen Vorräten passt. Zutaten, die in Kürze ablaufen (innerhalb der nächsten 30 Tage) oder bereits abgelaufen sind, verleihen dem Rezept automatisch einen **Score-Bonus von +15 %**, um Lebensmittelverschwendung aktiv zu verhindern.
- **MHD-Status pro Zutat (NEU):**
  - 🟥 **expired** → Zutat ist bereits abgelaufen
  - 🟧 **expiring** → Zutat läuft in den nächsten 30 Tagen ab
  - 🟩 **normal** → keine Auffälligkeit
- **Visuelle Frontend-Markierung:**
  - Abgelaufene Zutaten werden **rot und fett** dargestellt
  - Bald ablaufende Zutaten werden **orange und fett** dargestellt
  - Normale Zutaten bleiben standardmäßig formatiert
- **MHD-Warnindikator:** Rezepte mit kritischen Mindesthaltbarkeitsdaten erhalten ein Kennzeichen (`hasExpiring`), um im Frontend optisch markiert werden zu können.
- **8-Tage-Speiseplan-Filter:** Rezepte, die bereits für die nächsten 8 Tage im Mealie-Speiseplan eingetragen sind, werden automatisch aus den Vorschlägen ausgeblendet.
- **Dynamische Ausschlussliste mit Basics-Isolierung:** Standardzutaten und Gewürze (z. B. Salz, Pfeffer, Wasser, Öl) werden über die Integrations-Optionen ignoriert. Diese werden nun vollautomatisch bereinigt und separat zur hübschen Frontend-Anzeige bereitgestellt.

---

## ✨ Neu 

- **Strukturierte Zutaten-Objekte im Sensor:**
  - Zutaten werden nicht mehr als einfache Strings geliefert
  - Jede Zutat enthält nun:
    - `name`
    - `status` (`expired | expiring | normal`)
- **Klare visuelle Trennung im Dashboard:**
  - Verhindert Verwechslung zwischen „Einkaufen“, „läuft bald ab“ und „abgelaufen“
- **Feingranulare Farbsteuerung im Frontend:**
  - Statusbasierte Darstellung direkt im Lovelace UI möglich
- **Verbesserte Datenbasis für Automationen:**
  - Status kann nun auch für zukünftige Automationen genutzt werden (z. B. Benachrichtigungen oder Einkaufsempfehlungen)

Ab Version 0.2.5b5
<img width="511" height="757" alt="image" src="https://github.com/user-attachments/assets/f9dfaae3-9d62-4950-95e1-efe39bf625e4" />
 
- **Aktueller Speiseplan in der Karte (NEU):**
  - Optional direkt unterhalb der RezeptvorschlÃ¤ge sichtbar
  - Zeigt die laufende Samstag-bis-Samstag-Woche aus Mealie
- **BlÃ¤tterbare Rezeptseiten (NEU):**
  - Wenn mehr Rezepte vorhanden sind als angezeigt werden sollen, kann durch die restlichen VorschlÃ¤ge geblÃ¤ttert werden
  - Funktioniert auch in responsiven, schmalen Dashboard-Layouts
vier verschiedene Darstellungsmöglichkeiten

---

## 🛠️ Registrierte Dienste (Services)

Die Integration stellt nach der Installation zwei native Dienste zur Verfügung.

---

### 1. `mealie_grocy_bridge.set_to_next_free_day`

Nimmt das Rezept am angegebenen Index, sucht vollautomatisch den nächsten freien Tag (Typ: Abendessen/Dinner) im Mealie-Speiseplan der kommenden 30 Tage und bucht es dort ein.

*Zusätzlich wird eine native Home Assistant Push-Benachrichtigung mit dem Namen des Gerichts und dem gewählten Datum versendet.*

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*

---

### 2. `mealie_grocy_bridge.add_missing_ingredients`

Liest das Attribut `missingIngredients` des ausgewählten Rezept-Index aus und fügt jede fehlende Zutat einzeln als To-Do-Punkt zu deiner Einkaufsliste hinzu.

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*

---

## 🏗️ Systemarchitektur Backend

Die Integration basiert auf einer zentralen, schlanken Systemarchitektur.

### Sensor: `sensor.mealie_grocy_kochvorschlage`

Der Sensor läuft über einen `DataUpdateCoordinator` und aktualisiert standardmäßig alle **30 Minuten**.

Er stellt folgende Attribute bereit:

- `recipes` → Vollständige Rezeptliste mit Matching-Informationen
- `markdown_suggestions` → optionaler Text-Output
- `matchingIngredients` → strukturierte Zutatenliste mit Status
- `missingIngredients` → fehlende Zutaten pro Rezept
- `basicIngredients` → bereinigte Basiszutaten
- `hasExpiring` → Hinweis auf kritische Haltbarkeit

---

## 🎨 Dashboard-Integration (Lovelace Card)

Die Integration bringt eine maßgeschneiderte Lovelace-Karte (`MealieGrocyCard`) direkt mit.

### Visuelles Verhalten der Zutaten

| Status | Darstellung |
|--------|------------|
| `expired` | 🔴 Rot + Fett |
| `expiring` | 🟠 Orange + Fett |
| `normal` | Standardfarbe |

---

### 1. Karte als Ressource registrieren

1. **Einstellungen → Dashboards → Ressourcen**
2. **Ressource hinzufügen**
3. Eintragen:

- **URL:**  
  `/local/community/mealie_grocy_bridge/mealie-grocy-card.js?v=1.3`

- **Typ:**  
  `JavaScript-Modul`

---

### 2. Karten-Features

- Visueller Editor (ha-form)
- Automatische Spaltenanpassung
- Responsive Grid-System
- Keine Scrollbereiche innerhalb der Karten
- Dynamische Höhenanpassung pro Rezept

---

### 3. Konfiguration

| Parameter | Typ | Standard | Beschreibung |
|----------|-----|----------|--------------|
| `type` | String | Pflicht | `custom:mealie-grocy-card` |
| `entity` | String | `sensor.mealie_grocy_kochvorschlage` | Sensor-Entität |
| `recipe_count` | Integer | 4 | Anzahl der Rezepte |
| `recipes_per_row` | Integer | optional | Fixe Spaltenanzahl (leer lassen für Auto-Layout) |

---

### Automatischer Sektions-Modus (Empfohlen)

Die Karte passt sich dynamisch dem Home Assistant Layout an:

```yaml
type: custom:mealie-grocy-card
entity: sensor.mealie_grocy_kochvorschlage
recipe_count: 4
grid_options:
  columns: 24
  rows: auto
recipes_per_row: 4

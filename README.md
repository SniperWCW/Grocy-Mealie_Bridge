# Mealie-Grocy Bridge Integration für Home Assistant

Diese maßgeschneiderte Home Assistant Integration schließt die Lücke zwischen deiner Rezeptverwaltung (**Mealie**) und deiner Vorratsdatenbank (**Grocy**). Sie analysiert vollautomatisch im Hintergrund, welche Zutaten deiner Rezepte bereits im Haus sind, berechnet einen intelligenten Match-Score und erlaubt es dir, Mahlzeiten direkt zu planen oder fehlende Zutaten mit einem Klick auf deine Einkaufsliste zu setzen.

---

## 🚀 Features & Kernfunktionen

- **Automatischer API-Abgleich:** Vergleicht im Hintergrund Mealie-Rezeptzutaten direkt mit dem aktuellen Grocy-Warenbestand.
- **Intelligenter Match-Score mit MHD-Logik:** Berechnet prozentual, wie gut ein Rezept zu deinen vorhandenen Vorräten passt. Zutaten, die in Kürze ablaufen (innerhalb der nächsten 30 Tage) oder bereits abgelaufen sind, verleihen dem Rezept automatisch einen **Score-Bonus von +15 %**, um Lebensmittelverschwendung aktiv zu verhindern.
- **MHD-Warnindikator:** Rezepte mit kritischen Mindesthaltbarkeitsdaten erhalten ein Kennzeichen (`hasExpiring`), um im Frontend optisch markiert werden zu können.
- **8-Tage-Speiseplan-Filter:** Rezepte, die bereits für die nächsten 8 Tage im Mealie-Speiseplan eingetragen sind, werden automatisch aus den Vorschlägen ausgeblendet.
- **Dynamische Ausschlussliste mit Basics-Isolierung:** Standardzutaten und Gewürze (z. B. Salz, Pfeffer, Wasser, Öl) werden über die Integrations-Optionen ignoriert. Diese werden nun vollautomatisch bereinigt und separat zur hübschen Frontend-Anzeige bereitgestellt.

### ✨ Neu ab v0.3.0
- **Intelligente Basics-Formatierung:** Mengenangaben (z. B. `1 tl`, `4 el`, `¹/₄ tl`), Brüche und Zahlen am Anfang von Basis-Zutaten werden automatisch per Regex herausgefiltert. Die reinen Namen werden einheitlich mit großem Anfangsbuchstaben (**Capitalized**) formatiert (z. B. *pfeffer* ➔ *Pfeffer*), um eine unschöne Darstellung im Dashboard zu verhindern.
- **Isoliertes `basicIngredients` Attribut:** Ignorierte Basics werden nicht mehr verworfen, sondern als bereinigte Liste im Sensor-Attribut mitgeliefert.
- **Native Home Assistant Dienste:** Keine manuellen Jinja2-Skripte, Hilfskonstrukte oder Automatisierungen mehr nötig. Die gesamte Logik läuft performant direkt im Python-Kern der Integration.
- **Automatischer Sofort-Refresh:** Sobald ein Rezept über den integrierten Dienst auf den Speiseplan gesetzt wird, triggert die Bridge ein sofortiges Update des Sensors. Das geplante Gericht verschwindet ohne Verzögerung aus den Vorschlägen.
- **Ultra-intelligentes Teilwort-Matching (Sub-String):** Erkennt jetzt auch Grocy-Produkte anhand von Rezept-Teilwörtern (z. B. Mealie: `"Mehl"` ➔ Grocy: `"Weizenmehl Typ 405"`). Aktiv ab 4 Buchstaben, um Fehltreffer zu vermeiden.

---

## 🛠️ Registrierte Dienste (Services)

Die Integration stellt nach der Installation zwei native Dienste zur Verfügung. Diese arbeiten ultraschnell direkt mit dem internen **Rezept-Index** des Sensors (wobei `0` für das erste Rezept im Sensor steht, `1` für das zweite, etc.).

### 1. `mealie_grocy_bridge.set_to_next_free_day`
Nimmt das Rezept am angegebenen Index, sucht vollautomatisch den nächsten freien Tag (Typ: Abendessen/Dinner) im Mealie-Speiseplan der kommenden 30 Tage und bucht es dort ein. 
*Zusätzlich wird eine native Home Assistant Push-Benachrichtigung mit dem Namen des Gerichts und dem gewählten Datum versendet.*

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*: Die Position des Rezepts im Sensor (z. B. `0`).

### 2. `mealie_grocy_bridge.add_missing_ingredients`
Liest das Attribut `missingIngredients` des ausgewählten Rezept-Index aus und fügt jede fehlende Zutat einzeln als To-Do-Punkt zu deiner in den Integrations-Optionen festgelegten Einkaufsliste hinzu.

**Parameter:**
- `recipe_index` *(Mussfeld, Zahl)*: Die Position des Rezepts im Sensor (z. B. `0`).

---

## 🏗️ Systemarchitektur Backend

Die Integration basiert auf einer zentralen, schlanken Systemarchitektur:

### Der Sensor (`sensor.mealie_grocy_kochvorschlage`)
Der Sensor läuft über einen `DataUpdateCoordinator` und fragt standardmäßig alle **30 Minuten** die APIs von Mealie und Grocy ab. Er stellt die berechneten Daten in folgenden Attributen bereit:
- `recipes`: Ein strukturiertes JSON-Array mit den Rohdaten der Top-Rezepte (`recipeId`, `recipeName`, `matchScore`, `matchingIngredients`, `missingIngredients`, `basicIngredients`, `url`, `hasExpiring`).
- `markdown_suggestions`: Ein Textblock zur einfachen Darstellung.

---

## 🎨 Dashboard-Integration (Lovelace Card)

Die Integration bringt eine maßgeschneiderte Lovelace-Karte (`MealieGrocyCard`) direkt mit. Diese passt sich automatisch an dein Home Assistant Theme an, ist voll responsive für Smartphones optimiert und bietet native Buttons, um fehlende Zutaten auf die Einkaufsliste zu setzen oder das Rezept direkt in den Mealie-Speiseplan einzutragen.

### 1. Karte als Ressource registrieren

Da die Karte automatisch im lokalen Home Assistant Speicher abgelegt wird, musst du sie lediglich einmalig als Lovelace-Ressource registrieren:

1. Gehe in Home Assistant auf **Einstellungen** ➔ **Dashboards**.
2. Klicke oben rechts auf die drei Punkte und wähle **Ressourcen**.
3. Klicke unten rechts auf **Ressource hinzufügen**.
4. Trage folgende Werte ein:
   * **URL:** `/local/community/mealie_grocy_bridge/mealie-grocy-card.js?v=1.3` *(Tipp: Erhöhe die Versionsnummer am Ende nach einem Update, um den Browser-Cache zu zwingen, die neue Karte zu laden).*
   * **Ressourcentyp:** `JavaScript-Modul`

---

### 2. Visuelle Konfiguration & Features der Karte

Ab Version 1.3 bringt die Karte vollwertigen Support für moderne Dashboards mit und macht die manuelle YAML-Editierung überflüssig.

* **Echter Visueller Editor (`ha-form`):** Beim Hinzufügen oder Bearbeiten der Karte öffnet sich ein komfortables Formular. Die Sensor-Entität, die Gesamtanzahl der gewünschten Rezepte sowie die Spalten können komfortabel per Klick und Dropdown ausgewählt werden.
* **Nativer Support für das Abschnitte-Layout (Sections):** Die Karte ist voll kompatibel mit dem modernen 12-Spalten-Rastersystem von Home Assistant. Über den nativen Reiter **Layout** im Bearbeitungsmodus lässt sich die Karte flexibel per Schieberegler in der Breite verstellen (von 3 bis 12 Raster-Einheiten).
* **Dynamisches Höhen-Grid (Keine Scrollbalken mehr!):** Die Karte berechnet die Höhe der Rezeptkacheln komplett dynamisch (`grid-auto-rows: 1fr`). Alle Kacheln innerhalb einer Reihe passen sich automatisch flexibel an das Rezept mit dem längsten Text an. Es entstehen keine unschönen Scrollbalken und alle Zutaten bleiben stets zu 100 % sichtbar.

---

### 3. Konfigurations-Parameter (Visueller Editor / YAML)

| Parameter | Typ | Standard | Beschreibung |
| :--- | :--- | :--- | :--- |
| `type` | String | **Pflichtfeld** | Muss exakt `custom:mealie-grocy-card` lauten. |
| `entity` | String | `sensor.mealie_grocy_kochvorschlage` | Die Sensor-Entität deiner Bridge. Bequem im Editor wählbar. |
| `recipe_count` | Integer | `4` | **Gesamtanzahl** der Rezepte, die maximal aus dem Sensor geladen und auf der Karte dargestellt werden. |
| `recipes_per_row` | Integer | *Optional* | **Spalten (Erzwingen):** Wird hier eine Zahl eingetragen, bricht die Karte starr nach dieser Spaltenanzahl um. **Empfehlung:** Feld leer lassen, damit sich die Spaltenanzahl vollautomatisch nach dem Schieberegler des Sektions-Layouts richtet. |

---

### 4. YAML-Beispiele (Für fortgeschrittene Nutzung)
<img width="250" height="394" alt="image" src="https://github.com/user-attachments/assets/f9fe734a-d0fc-4235-8d4d-5c3ad5f8ea0e" />
<img width="504" height="357" alt="image" src="https://github.com/user-attachments/assets/e62415c3-bb4c-4baa-b5fe-8ac959bc89d0" />


#### Automatischer Sektions-Modus (Empfohlen)
Nutzt den visuellen Schieberegler im Abschnitte-Layout zur Breitensteuerung. Das Raster berechnet sich vollautomatisch (12 Einheiten Breite = 4 Spalten Rezepte, 6 Einheiten Breite = 2 Spalten Rezepte):
```yaml
type: custom:mealie-grocy-card
recipe_count: 4
grid_options:
  columns: 24
  rows: auto
entity: sensor.mealie_grocy_kochvorschlage
recipes_per_row: 4

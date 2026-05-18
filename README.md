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

## 📺 Frontend-Beispiele (Lovelace Dashboard)
## 🎨 Dashboard-Integration (Lovelace Card)

Die Integration bringt eine maßgeschneiderte Lovelace-Karte (`MealieGrocyCard`) direkt mit. Diese passt sich automatisch an dein Home Assistant Theme an, ist voll responsive für Smartphones optimiert und bietet native Buttons, um fehlende Zutaten auf die Einkaufsliste zu setzen oder das Rezept direkt in den Mealie-Speiseplan einzutragen.

### 1. Karte als Ressource registrieren

Da die Karte automatisch im lokalen Home Assistant Speicher abgelegt wird, musst du sie lediglich einmalig als Lovelace-Ressource registrieren:

1. Gehe in Home Assistant auf **Einstellungen** ➔ **Dashboards**.
2. Klicke oben rechts auf die drei Punkte und wähle **Ressourcen**.
3. Klicke unten rechts auf **Ressource hinzufügen**.
4. Trage folgende Werte ein:
   * **URL:** `/local/community/mealie_grocy_bridge/mealie-grocy-card.js?v=1.1` *(Tipp: Erhöhe die Versionsnummer am Ende nach einem Update, um den Browser-Cache zu zwingen, die neue Karte zu laden).*
   * **Ressourcentyp:** `JavaScript-Modul`

---

### 2. Konfiguration im Dashboard

Füge deinem Dashboard eine neue Karte hinzu und wechsle in den **Code-Editor (YAML)**. Die Karte bietet dir volle Flexibilität bei der Anzahl der Spalten und der Menge der angezeigten Rezepte.

#### Konfigurations-Parameter:

| Parameter | Typ | Standard | Beschreibung |
| :--- | :--- | :--- | :--- |
| `type` | String | **Pflichtfeld** | Muss exakt `custom:mealie-grocy-card` lauten. |
| `entity` | String | `sensor.mealie_grocy_kochvorschlage` | Die Sensor-Entität deiner Bridge. |
| `recipes_per_row` | Integer | `1` | Maximale Anzahl an Rezeptkacheln, die **nebeneinander** in einer Reihe angezeigt werden. |
| `recipe_count` | Integer | `4` | **Gesamtanzahl** der Rezepte, die maximal aus dem Sensor geladen und auf der Karte dargestellt werden. |

---

### 3. YAML-Beispiele

#### Standard-Ansicht (Raster-Layout)
Zeigt die Top 4 Rezepte sauber aufgeteilt in Zweierreihen an:
```yaml
type: custom:mealie-grocy-card
entity: sensor.mealie_grocy_kochvorschlage
recipes_per_row: 2
recipe_count: 4


// --------------------------------------------------------------------------------------
// IMPORT: Laden der benötigten Basis-Bibliotheken von LitElement über ein externes CDN.
// LitElement hilft dabei, performante und reaktive Custom Components für HA zu bauen.
// --------------------------------------------------------------------------------------
import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class MealieGrocyCard extends LitElement {
  
  // --------------------------------------------------------------------------------------
  // PROPERTIES: Definition der reaktiven Variablen.
  // Wenn Home Assistant ('hass') neue Sensordaten liefert oder sich die Dashboard-Konfiguration
  // ('config') ändert, triggert LitElement automatisch das Neuzeichnen (render) der Karte.
  // --------------------------------------------------------------------------------------
  static get properties() {
    return {
      hass: {},
      config: {}
    };
  }

  // --------------------------------------------------------------------------------------
  // STYLES (CSS): Das visuelle Design der Karte.
  // Eingekapselt via Shadow DOM, damit dieses CSS das restliche Dashboard nicht beeinflusst.
  // --------------------------------------------------------------------------------------
  static get styles() {
    return css`
      /* Basis-Host-Element (Die Karte selbst) */
      :host {
        display: block;
        width: 100%;
        height: 100%;
      }

      /* Das äußere ha-card Element von Home Assistant, das nun als sauberer Container dient */
      ha-card {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        width: 100%;
        height: 100%;
      }
      
      /* Das Grid-Layout, das die einzelnen Rezeptkacheln beinhaltet */
      .recipe-grid {
        display: grid;
        /* Dynamische Spaltenanzahl: Holt sich die Anzahl aus der CSS-Variable --recipes-per-row,
           die wir weiter unten im render() anhand deiner Config setzen. Jede Spalte ist min. 240px breit. */
        grid-template-columns: repeat(var(--recipes-per-row, 1), minmax(240px, 1fr));
        gap: 16px;
        padding: 4px;
        width: 100%;
        box-sizing: border-box;
      }
      
      /* SMARTPHONE-OPTIMIERUNG (Responsive Design): 
         Sobald der Bildschirm schmaler als 600px wird (z.B. Handy im Hochformat),
         brechen wir das Grid hart auf 1 Spalte um, damit nichts gequetscht wird. */
      @media (max-width: 600px) {
        .recipe-grid {
          grid-template-columns: 1fr !important;
        }
      }

      /* Das Design einer einzelnen Rezept-Kachel */
      .recipe-card {
        /* Nutzt HA-Theme-Variablen für den Hintergrund, fällt im Notfall auf Sekundär-Hintergrund zurück */
        background: var(--card-background-color, var(--secondary-background-color));
        border-radius: var(--bubble-border-radius, 20px);
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.05);
        padding: 16px;
        /* Festes 3-Zeilen-Raster: 1. Titel, 2. Zutaten (flexibler Rest), 3. Buttons ganz unten */
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 12px;
        height: 380px; /* Feste Kachelhöhe, damit alle Kacheln in einer Reihe exakt gleich lang sind */
        box-sizing: border-box;
      }

      /* Titelbereich (Rezeptname & Score) */
      .title-zone h3 {
        margin: 0 0 4px 0;
        font-size: 1.05rem;
        line-height: 1.2;
        text-transform: uppercase;
        /* Schneidet zu lange Rezeptnamen nach exakt 2 Zeilen mit "..." ab, falls sie zu lang sind */
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      /* Der Link zum originalen Mealie-Rezept */
      .recipe-link {
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 2px;
      }

      /* Die mittlere Inhaltszone für die Zutaten (mit Scrollbalken-Logik) */
      .content-zone {
        font-size: 0.85rem;
        line-height: 1.3;
        display: flex;
        flex-direction: column;
        gap: 8px;
        overflow-y: auto; /* Aktiviert den vertikalen Scrollbalken, falls die Zutatenliste sehr lang wird */
        padding-right: 4px;
      }

      /* Styling des dezenten Scrollbalkens in der Inhaltszone */
      .content-zone::-webkit-scrollbar {
        width: 4px;
      }
      .content-zone::-webkit-scrollbar-thumb {
        background: rgba(var(--rgb-primary-text-color), 0.1);
        border-radius: 4px;
      }

      /* Einzelne Text-Abschnitte (Vorhanden, Basics, Einkaufen) */
      .ingredient-section {
        display: block;
      }

      /* Die fettgedruckten Labels vor den Zutatenlisten */
      .ingredient-label {
        font-weight: bold;
        display: block;
        color: var(--primary-text-color);
        margin-bottom: 1px;
      }

      /* Die eigentliche Liste der Text-Zutaten */
      .ingredient-list {
        color: var(--secondary-text-color);
        display: inline;
      }

      /* Spezielles Styling für die Fehlenden ("Einkaufen") Zutaten */
      .missing {
        font-style: italic;
        color: var(--warning-color, #d32f2f); /* Rote Warnfarbe aus dem HA-Theme */
      }

      /* Die untere Aktions-Zone für die beiden Buttons */
      .action-zone {
        display: flex;
        justify-content: center;
        gap: 24px;
        border-top: 1px solid rgba(var(--rgb-primary-text-color), 0.08); /* Trennstrich nach oben */
        padding-top: 12px;
      }

      /* Das Design der runden Aktions-Buttons */
      .btn {
        background: rgba(var(--rgb-primary-text-color), 0.03);
        border: none;
        border-radius: 50%; /* Macht den Button kreisrund */
        width: 42px;
        height: 42px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s; /* Sanftes Aufleuchten beim Drüberfahren */
      }

      /* Hover-Effekt, wenn man mit der Maus über die Buttons fährt */
      .btn:hover {
        background: rgba(var(--rgb-primary-text-color), 0.08);
      }
    `;
  }

  // --------------------------------------------------------------------------------------
  // RENDER: Das HTML-Grundgerüst der Karte, welches dynamisch befüllt wird.
  // --------------------------------------------------------------------------------------
  render() {
    // Sicherheitsabfrage: Wenn HA oder die Konfiguration noch lädt, brich ab
    if (!this.hass || !this.config) return html``;

    // Ermittle die konfigurierte Sensor-Entity (oder nutze unseren Standard)
    const entityId = this.config.entity || 'sensor.mealie_grocy_kochvorschlage';
    const stateObj = this.hass.states[entityId];
    
    // Fehler abfangen, falls der Sensor (noch) keine Daten liefert
    if (!stateObj || !stateObj.attributes.recipes) {
      return html`<ha-card style="padding: 16px;">Warte auf Daten vom Mealie-Grocy-Sensor...</ha-card>`;
    }

    // ERWEITERUNG: Liest aus, wie viele Rezepte insgesamt angezeigt werden sollen (Standard: 4)
    const recipeCount = this.config.recipe_count || 4;

    // Wir schneiden das Array anhand des neuen "recipe_count" Parameters flexibel ab
    const recipes = stateObj.attributes.recipes.slice(0, recipeCount);
    
    // Liest aus, wie viele Rezepte pro Reihe im Dashboard gewünscht sind (Standard: 1)
    const perRow = this.config.recipes_per_row || 1;

    return html`
      <ha-card>
        <div class="recipe-grid" style="--recipes-per-row: ${perRow};">
          
          ${recipes.map((recipe, index) => html`
            <div class="recipe-card">
              
              <div class="title-zone">
                <h3>🍳 ${recipe.recipeName} ${recipe.hasExpiring ? '🔥' : ''}</h3>
                <div>📊 Score: <strong>${recipe.matchScore}%</strong></div>
                
                ${recipe.url ? html`
                  <a class="recipe-link" href="${recipe.url}" target="_blank">
                    👉 REZEPT ÖFFNEN <ha-icon icon="mdi:open-in-new" style="--mdc-icon-size: 14px;"></ha-icon>
                  </a>
                ` : ''}
              </div>

              <div class="content-zone">
                
                <div class="ingredient-section">
                  <span class="ingredient-label">✅ Vorhanden:</span>
                  <div class="ingredient-list">
                    ${recipe.matchingIngredients && recipe.matchingIngredients.length > 0 
                      ? recipe.matchingIngredients.map(i => i.charAt(0).toUpperCase() + i.slice(1)).join(', ') 
                      : 'Keine'}
                  </div>
                </div>
                
                <div class="ingredient-section">
                  <span class="ingredient-label">🧂 Basics (Ignoriert):</span>
                  <div class="ingredient-list">
                    ${recipe.basicIngredients && recipe.basicIngredients.length > 0 
                      ? recipe.basicIngredients.map(i => i.charAt(0).toUpperCase() + i.slice(1)).join(', ') 
                      : 'Keine'}
                  </div>
                </div>

                <div class="ingredient-section">
                  <span class="ingredient-label">🛒 Einkaufen:</span>
                  <div class="ingredient-list missing">
                    ${recipe.missingIngredients && recipe.missingIngredients.length > 0 
                      ? recipe.missingIngredients.map(i => i.trim().charAt(0).toUpperCase() + i.trim().slice(1)).join(', ') 
                      : 'Nichts'}
                  </div>
                </div>
              </div>

              <div class="action-zone">
                <button class="btn" title="Fehlende Zutaten auf Einkaufsliste" @click="${() => this._callBridgeService('add_missing_ingredients', index)}">
                  <ha-icon icon="mdi:cart-plus" style="color: var(--primary-color);"></ha-icon>
                </button>
                
                <button class="btn" title="In den Mealplan eintragen" @click="${() => this._callBridgeService('set_to_next_free_day', index)}">
                  <ha-icon icon="mdi:calendar-plus" style="color: var(--info-color);"></ha-icon>
                </button>
              </div>

            </div>
          `)}
        </div>
      </ha-card>
    `;
  }

  // --------------------------------------------------------------------------------------
  // NATIVE LAYOUT INTEGRATION: Aktiviert die "Layout"-Optionen im Dashboard-Editor.
  // --------------------------------------------------------------------------------------
  static getGridOptions(config) {
    return {
      columns: 4,        // Standardmäßige Breite im Grid-Layout (4 Spalten)
      rows: "auto",      
      min_columns: 1,
      max_columns: 4,
    };
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_kochvorschlage",
      recipes_per_row: 2,
      recipe_count: 4 // Standardmäßig zeigen wir weiterhin 4 Vorschläge
    };
  }

  // --------------------------------------------------------------------------------------
  // HILFSFUNKTION: Service-Aufruf an Home Assistant.
  // --------------------------------------------------------------------------------------
  _callBridgeService(serviceName, index) {
    this.hass.callService('mealie_grocy_bridge', serviceName, {
      recipe_index: index
    });
  }

  // --------------------------------------------------------------------------------------
  // SET CONFIG: Wird von HA aufgerufen, um die UI-Optionen der Karte zu übergeben.
  // --------------------------------------------------------------------------------------
  setConfig(config) {
    this.config = config;
  }

  // --------------------------------------------------------------------------------------
  // GET CARD SIZE: Gibt HA eine ungefähre Vorstellung davon, wie hoch die Karte ist
  // --------------------------------------------------------------------------------------
  getCardSize() {
    return 4;
  }
}

// Registriert unsere Custom Component im Browser, damit HA das Tag <mealie-grocy-card> kennt.
customElements.define("mealie-grocy-card", MealieGrocyCard);

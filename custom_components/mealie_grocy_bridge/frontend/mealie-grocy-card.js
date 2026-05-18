// --------------------------------------------------------------------------------------
// IMPORT: Laden der benötigten Basis-Bibliotheken von LitElement über ein externes CDN.
// --------------------------------------------------------------------------------------
import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

// ======================================================================================
// EDITOR-KLASSE: Das visuelle Formular in der Dashboard-Konfiguration
// ======================================================================================
class MealieGrocyCardEditor extends LitElement {
  
  static get properties() {
    return {
      hass: {},
      _config: {}
    };
  }

  setConfig(config) {
    this._config = config;
  }

  // Definition des Formular-Schemas für den visuellen Editor
  _getSchema() {
    return [
      { name: "entity", label: "Sensor Entität", selector: { entity: { domain: "sensor" } } },
      { 
        name: "", 
        type: "grid", 
        column_min_width: "100px",
        schema: [
          { name: "recipe_count", label: "Anzahl Rezepte gesamt", selector: { number: { min: 1, max: 20, mode: "box" } } },
          { name: "recipes_per_row", label: "Spalten (Klassisch)", selector: { number: { min: 1, max: 6, mode: "box" } } }
        ]
      }
    ];
  }

  render() {
    if (!this.hass || !this._config) return html``;

    return html`
      <ha-form
        .hass=${this.hass}
        .data=${this._config}
        .schema=${this._getSchema()}
        .computeLabel=${(schema) => schema.label}
        @value-changed=${this._valueChanged}
      ></ha-form>
      <div style="padding: 16px; border-top: 1px solid var(--divider-color); margin-top: 16px; font-size: 0.9rem; color: var(--secondary-text-color);">
        💡 <strong>Tipp:</strong> Im neuen "Abschnitte"-Layout steuert der Reiter <strong>Layout</strong> (oben) die echte Breite. Die "Spalten"-Einstellung hier dient als Fallback für ältere Dashboards.
      </div>
    `;
  }

  // Diese Funktion wird aufgerufen, wenn du im UI etwas änderst
  _valueChanged(ev) {
    const config = ev.detail.value;
    const event = new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}
customElements.define("mealie-grocy-card-editor", MealieGrocyCardEditor);


// ======================================================================================
// HAUPT-KLASSE: Die eigentliche Rezeptkarte
// ======================================================================================
class MealieGrocyCard extends LitElement {
  
  static get properties() {
    return {
      hass: {},
      config: {}
    };
  }

  // Verknüpfung zum Editor
  static getConfigElement() {
    return document.createElement("mealie-grocy-card-editor");
  }

  static get styles() {
    return css`
      :host {
        display: block;
        width: 100%;
      }

      ha-card {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        width: 100%;
        display: block;
      }
      
      .recipe-grid {
        display: grid;
        /* Dynamische Spalten: Nutzt HA-Layout oder die manuelle Einstellung */
        grid-template-columns: repeat(var(--calculated-columns, var(--recipes-per-row, 4)), minmax(0, 1fr));
        grid-auto-rows: 1fr;
        gap: 16px;
        padding: 4px;
        width: 100%;
        box-sizing: border-box;
      }
      
      @media (max-width: 600px) {
        .recipe-grid {
          grid-template-columns: 1fr !important;
          grid-auto-rows: auto !important;
        }
      }

      .recipe-card {
        background: var(--card-background-color, var(--secondary-background-color));
        border-radius: var(--bubble-border-radius, 20px);
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.05);
        padding: 16px;
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 12px;
        min-height: 380px;
        height: 100%;
        box-sizing: border-box;
        width: 100%;
      }

      .title-zone h3 {
        margin: 0 0 4px 0;
        font-size: 1.05rem;
        line-height: 1.2;
        text-transform: uppercase;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

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

      .content-zone {
        font-size: 0.85rem;
        line-height: 1.3;
        display: flex;
        flex-direction: column;
        gap: 8px;
        overflow: visible;
      }

      .ingredient-section {
        display: block;
      }

      .ingredient-label {
        font-weight: bold;
        display: block;
        color: var(--primary-text-color);
        margin-bottom: 1px;
      }

      .ingredient-list {
        color: var(--secondary-text-color);
        display: inline;
      }

      .missing {
        font-style: italic;
        color: var(--warning-color, #d32f2f);
      }

      .action-zone {
        display: flex;
        justify-content: center;
        gap: 24px;
        border-top: 1px solid rgba(var(--rgb-primary-text-color), 0.08);
        padding-top: 12px;
      }

      .btn {
        background: rgba(var(--rgb-primary-text-color), 0.03);
        border: none;
        border-radius: 50%;
        width: 42px;
        height: 42px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
      }

      .btn:hover {
        background: rgba(var(--rgb-primary-text-color), 0.08);
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    const entityId = this.config.entity || 'sensor.mealie_grocy_kochvorschlage';
    const stateObj = this.hass.states[entityId];
    
    if (!stateObj || !stateObj.attributes.recipes) {
      return html`<ha-card style="padding: 16px;">Warte auf Daten vom Mealie-Grocy-Sensor...</ha-card>`;
    }

    // NUTZT JETZT DIE EINSTELLUNG AUS DEM VISUELLEN EDITOR (Standard: 4)
    const recipeLimit = this.config.recipe_count || 4;
    const recipes = stateObj.attributes.recipes.slice(0, recipeLimit);
    
    // Spalten-Berechnung
    const haColumns = this.config.layout?.grid_columns || 12;
    let calculatedColumns = this.config.recipes_per_row || 4;
    
    if (haColumns > 4) {
      calculatedColumns = Math.max(1, Math.round(haColumns / 3));
    } else {
      calculatedColumns = haColumns;
    }

    return html`
      <ha-card>
        <div class="recipe-grid" style="--calculated-columns: ${calculatedColumns};">
          
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

  getLayoutOptions() {
    return {
      grid_rows: "auto",
      grid_columns: this.config.layout?.grid_columns || 12,      
      grid_min_columns: 3,   
      grid_max_columns: 12,  
    };
  }

  static getLayoutOptions() {
    return {
      grid_rows: "auto",
      grid_columns: 12,
      grid_min_columns: 3,
      grid_max_columns: 12,
    };
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_kochvorschlage",
      recipe_count: 4,
      recipes_per_row: 4
    };
  }

  _callBridgeService(serviceName, index) {
    this.hass.callService('mealie_grocy_bridge', serviceName, {
      recipe_index: index
    });
  }

  setConfig(config) {
    this.config = config;
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("mealie-grocy-card", MealieGrocyCard);

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

  _getSchema() {
    return [
      { name: "entity", label: "Sensor Entität", selector: { entity: { domain: "sensor" } } },

      {
        name: "display_mode",
        label: "Darstellung",
        selector: {
          select: {
            options: [
              { value: "default", label: "Standard – Vollansicht " },
              { value: "mini", label: "Mini – kompakter, weniger Höhe" },
              { value: "compact", label: "Kompakt – sehr platzsparend, ideal für 4–6 Spalten" },
              { value: "list", label: "Liste – extrem kompakt, eine Zeile pro Rezept" }
            ]
          }
        }
      },

      { 
        name: "", 
        type: "grid", 
        column_min_width: "100px",
        schema: [
          { name: "recipe_count", label: "Anzahl Rezepte gesamt", selector: { number: { min: 1, max: 20, mode: "box" } } },
          { name: "recipes_per_row", label: "Spalten (Erzwingen)", selector: { number: { min: 1, max: 6, mode: "box" } } }
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
        💡 <strong>Hinweis zur Spaltenwahl:</strong><br>
        Wenn du hier eine Zahl bei <strong>Spalten (Erzwingen)</strong> einträgst, wird das Raster starr darauf fixiert. Lässt du das Feld leer (oder löschst die Zahl), kannst du die Breite wieder flexibel über den Reiter <strong>Layout</strong> oben mit dem Schieberegler steuern.
      </div>
    `;
  }

  _valueChanged(ev) {
    const config = ev.detail.value;
    
    if (config.recipes_per_row === "") delete config.recipes_per_row;
    if (config.recipe_count === "") delete config.recipe_count;

    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
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
        grid-template-columns: repeat(var(--calculated-columns, 4), minmax(0, 1fr));
        gap: 16px;
        padding: 4px;
        width: 100%;
      }
      
      @media (max-width: 600px) {
        .recipe-grid {
          grid-template-columns: 1fr !important;
        }
      }

      /* ---------------------------------------------------------
         BASIS-KARTE (Variante 1 – default)
      --------------------------------------------------------- */
      .recipe-card {
        background: var(--card-background-color, var(--secondary-background-color));
        border-radius: var(--bubble-border-radius, 20px);
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.05);
        padding: 16px;
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 12px;
        min-height: 380px;
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

      .content-zone {
        font-size: 0.85rem;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .ingredient-label {
        font-weight: bold;
        display: block;
        margin-bottom: 1px;
      }

      .expired {
        color: #ff5252;
        font-weight: bold;
      }

      .expiring {
        color: orange;
        font-weight: bold;
      }

      .missing {
        opacity: 0.85;
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
        border-radius: 50%;
        width: 42px;
        height: 42px;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      /* ---------------------------------------------------------
         VARIANTE 2 – MINI
      --------------------------------------------------------- */
      .recipe-card.mini {
        min-height: 240px;
        padding: 12px;
        gap: 8px;
      }

      .recipe-card.mini h3 {
        font-size: 0.9rem;
        -webkit-line-clamp: 1;
      }

      /* ---------------------------------------------------------
         VARIANTE 3 – COMPACT
      --------------------------------------------------------- */
      .recipe-card.compact {
        min-height: 180px;
        padding: 10px;
        gap: 6px;
      }

      .recipe-card.compact .content-zone {
        font-size: 0.7rem;
        gap: 2px;
      }

      .recipe-card.compact .btn {
        width: 28px;
        height: 28px;
      }

      /* ---------------------------------------------------------
         VARIANTE 4 – LIST
      --------------------------------------------------------- */
      .recipe-card.list {
        padding: 8px 12px;
        min-height: auto;
        display: flex;
        align-items: center;
      }

      .recipe-card.list .title-zone,
      .recipe-card.list .content-zone,
      .recipe-card.list .action-zone {
        display: none;
      }

      .recipe-card.list::after {
        content: attr(data-list-text);
        font-size: 0.85rem;
        width: 100%;
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

    const recipeLimit = this.config.recipe_count || 4;
    const recipes = stateObj.attributes.recipes.slice(0, recipeLimit);

    const mode = this.config.display_mode || "default";

    let calculatedColumns = this.config.recipes_per_row;
    if (!calculatedColumns) {
      const haColumns = this.config.layout?.grid_columns || 12;
      calculatedColumns = haColumns > 4 ? Math.max(1, Math.round(haColumns / 3)) : haColumns;
    }

    return html`
      <ha-card>
        <div class="recipe-grid" style="--calculated-columns: ${calculatedColumns};">
          
          ${recipes.map((recipe, index) => {
            const listText = `🍳 ${recipe.recipeName} — ${recipe.matchScore}% — 🛒 ${recipe.missingIngredients.join(', ') || '–'}`;

            return html`
              <div class="recipe-card ${mode}" data-list-text="${listText}">
                
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
                        ? recipe.matchingIngredients.map(i => {
                            
                            const name = i.name
                              ? i.name.charAt(0).toUpperCase() + i.name.slice(1)
                              : 'Unbekannt';

                            if (i.status === "expired") {
                              return html`<span class="expired">${name}</span>`;
                            }

                            if (i.status === "expiring") {
                              return html`<span class="expiring">${name}</span>`;
                            }

                            return html`${name}`;

                          }).reduce((prev, curr, index) => [
                            prev,
                            index > 0 ? ', ' : '',
                            curr
                          ], [])
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
                  <button class="btn" @click="${() => this._callBridgeService('add_missing_ingredients', index)}">
                    <ha-icon icon="mdi:cart-plus"></ha-icon>
                  </button>
                  <button class="btn" @click="${() => this._callBridgeService('set_to_next_free_day', index)}">
                    <ha-icon icon="mdi:calendar-plus"></ha-icon>
                  </button>
                </div>

              </div>
            `;
          })}
        </div>
      </ha-card>
    `;
  }

  static getLayoutOptions(config) {
    const haColumns = config?.layout?.grid_columns || 12;
    return {
      grid_rows: "auto",
      grid_columns: haColumns,
      grid_min_columns: 3,
      grid_max_columns: 12,
    };
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_kochvorschlage",
      recipe_count: 4,
      display_mode: "default"
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

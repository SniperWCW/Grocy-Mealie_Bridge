import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class MealieGrocyCard extends LitElement {
  static get properties() {
    return {
      hass: {},
      config: {}
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .recipe-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
        padding: 4px;
      }
      .recipe-card {
        background: var(--card-background-color, var(--secondary-background-color));
        border-radius: var(--bubble-border-radius, 20px);
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.05);
        padding: 16px;
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 12px;
        min-height: 400px; /* Garantiert perfekte Symmetrie auf allen Geräten */
        box-sizing: border-box;
        position: relative;
      }
      .title-zone h3 {
        margin: 0 0 4px 0;
        font-size: 1.1rem;
        line-height: 1.3;
        text-transform: uppercase;
      }
      .recipe-link {
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.85rem;
        font-weight: bold;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 4px;
      }
      .recipe-link:hover {
        text-decoration: underline;
      }
      .content-zone {
        font-size: 0.9rem;
        line-height: 1.4;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .ingredient-section {
        display: block;
      }
      .ingredient-label {
        font-weight: bold;
        display: block;
        margin-bottom: 2px;
      }
      .ingredient-list {
        color: var(--secondary-text-color);
        padding-left: 4px;
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
        margin-top: 4px;
      }
      .btn {
        background: rgba(var(--rgb-primary-text-color), 0.03);
        border: none;
        border-radius: 50%;
        width: 44px;
        height: 44px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s ease-in-out;
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

    const recipes = stateObj.attributes.recipes.slice(0, 4);

    return html`
      <div class="recipe-grid">
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
    `;
  }

  _callBridgeService(serviceName, index) {
    // Ruft den Service der Integration auf (Domain: mealie_grocy_bridge)
    this.hass.callService('mealie_grocy_bridge', serviceName, {
      recipe_index: index
    });
  }

  setConfig(config) {
    this.config = config;
  }

  getCardSize() {
    return 3;
  }
}

customElements.define("mealie-grocy-card", MealieGrocyCard);

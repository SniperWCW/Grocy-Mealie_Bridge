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
        width: 100%;
      }

      ha-card {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        width: 100%;
      }

      /* =========================
         GRID
      ========================= */
      .recipe-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 18px;
        padding: 6px;
        align-items: stretch;
      }

      /* =========================
         CARD (Netflix Style)
      ========================= */
      .recipe-card {
        background: var(--card-background-color, #1c1c1c);
        border-radius: 18px;

        padding: 16px;
        display: flex;
        flex-direction: column;

        height: 360px;
        box-sizing: border-box;

        position: relative;
        overflow: hidden;

        transition: transform 0.25s ease, box-shadow 0.25s ease;
        will-change: transform;

        border: 1px solid rgba(255, 255, 255, 0.06);
      }

      .recipe-card:hover {
        transform: scale(1.04) translateY(-4px);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
        z-index: 10;
      }

      /* =========================
         TITLE
      ========================= */
      .title-zone h3 {
        margin: 0;
        font-size: 1.05rem;
        line-height: 1.2;
        color: var(--primary-text-color);
        text-transform: uppercase;

        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .score {
        margin-top: 6px;
        font-size: 0.85rem;
        opacity: 0.8;
      }

      /* =========================
         RECIPE LINK
      ========================= */
      .recipe-link {
        display: inline-flex;
        margin-top: 8px;
        font-size: 0.8rem;
        color: #e50914;
        text-decoration: none;
        font-weight: 600;
        gap: 6px;
        transition: opacity 0.2s ease;
      }

      .recipe-link:hover {
        opacity: 0.7;
      }

      /* =========================
         CONTENT
      ========================= */
      .content-zone {
        flex: 1;
        margin-top: 10px;

        display: flex;
        flex-direction: column;
        gap: 10px;

        font-size: 0.85rem;
        overflow: hidden;
      }

      .ingredient-section {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .ingredient-label {
        font-weight: 600;
        font-size: 0.75rem;
        opacity: 0.8;
      }

      .ingredient-list {
        color: var(--secondary-text-color);
        font-size: 0.82rem;
      }

      .missing {
        color: #ff6b6b;
        font-style: italic;
      }

      /* =========================
         ACTION BAR
      ========================= */
      .action-zone {
        margin-top: auto;

        display: flex;
        justify-content: space-between;
        align-items: center;

        padding-top: 12px;
        border-top: 1px solid rgba(255,255,255,0.08);
      }

      .btn {
        width: 42px;
        height: 42px;

        border-radius: 50%;
        border: none;

        background: rgba(255,255,255,0.06);

        display: flex;
        align-items: center;
        justify-content: center;

        cursor: pointer;

        transition: transform 0.2s ease, background 0.2s ease;
      }

      .btn:hover {
        transform: scale(1.15);
        background: rgba(255,255,255,0.12);
      }

      @media (max-width: 600px) {
        .recipe-card {
          height: auto;
        }
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    const entityId = this.config.entity || "sensor.mealie_grocy_kochvorschlage";
    const stateObj = this.hass.states[entityId];

    if (!stateObj?.attributes?.recipes) {
      return html`
        <ha-card style="padding:16px;">
          Warte auf Rezeptdaten...
        </ha-card>
      `;
    }

    const recipeCount = this.config.recipe_count || 6;
    const recipes = stateObj.attributes.recipes.slice(0, recipeCount);

    return html`
      <ha-card>
        <div class="recipe-grid">

          ${recipes.map((recipe, index) => html`
            <div class="recipe-card">

              <div class="title-zone">
                <h3>🍳 ${recipe.recipeName}</h3>

                <div class="score">
                  📊 ${recipe.matchScore}% Match
                </div>

                ${recipe.url ? html`
                  <a class="recipe-link" href="${recipe.url}" target="_blank">
                    👉 Rezept öffnen
                  </a>
                ` : ""}
              </div>

              <div class="content-zone">

                <div class="ingredient-section">
                  <div class="ingredient-label">Vorhanden</div>
                  <div class="ingredient-list">
                    ${recipe.matchingIngredients?.join(", ") || "Keine"}
                  </div>
                </div>

                <div class="ingredient-section">
                  <div class="ingredient-label">Basics</div>
                  <div class="ingredient-list">
                    ${recipe.basicIngredients?.join(", ") || "Keine"}
                  </div>
                </div>

                <div class="ingredient-section">
                  <div class="ingredient-label">Fehlt</div>
                  <div class="ingredient-list missing">
                    ${recipe.missingIngredients?.join(", ") || "Nichts"}
                  </div>
                </div>

              </div>

              <div class="action-zone">

                <button class="btn"
                  title="Einkaufsliste"
                  @click="${() => this._callBridgeService("add_missing_ingredients", index)}">
                  🛒
                </button>

                <button class="btn"
                  title="Planen"
                  @click="${() => this._callBridgeService("set_to_next_free_day", index)}">
                  📅
                </button>

              </div>

            </div>
          `)}

        </div>
      </ha-card>
    `;
  }

  _callBridgeService(serviceName, index) {
    this.hass.callService("mealie_grocy_bridge", serviceName, {
      recipe_index: index
    });
  }

  setConfig(config) {
    this.config = config;
  }

  getLayoutOptions() {
    return {
      grid_rows: "auto",
      grid_columns: "full"
    };
  }

  static getLayoutOptions() {
    return {
      grid_rows: "auto",
      grid_columns: "full"
    };
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_kochvorschlage",
      recipe_count: 6
    };
  }
}

customElements.define("mealie-grocy-card", MealieGrocyCard);

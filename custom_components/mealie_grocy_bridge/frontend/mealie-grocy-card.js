import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class MealieGrocyCardEditor extends LitElement {
  static get properties() {
    return {
      hass: {},
      _config: {},
    };
  }

  setConfig(config) {
    this._config = config;
  }

  _getSchema() {
    return [
      { name: "entity", label: "Sensor Entitat", selector: { entity: { domain: "sensor" } } },
      {
        name: "display_mode",
        label: "Darstellung",
        selector: {
          select: {
            options: [
              { value: "default", label: "Standard - Vollansicht" },
              { value: "mini", label: "Mini - kompakter, weniger Hohe" },
              { value: "compact", label: "Kompakt - sehr platzsparend, ideal fur 4-6 Spalten" },
              { value: "list", label: "Liste - extrem kompakt, eine Zeile pro Rezept" },
            ],
          },
        },
      },
      {
        name: "",
        type: "grid",
        column_min_width: "100px",
        schema: [
          { name: "recipe_count", label: "Anzahl Rezepte gesamt", selector: { number: { min: 1, max: 20, mode: "box" } } },
          { name: "recipes_per_row", label: "Spalten (Erzwingen)", selector: { number: { min: 1, max: 6, mode: "box" } } },
          { name: "show_current_week_mealplan", label: "Aktuellen Speiseplan unten anzeigen", selector: { boolean: {} } },
        ],
      },
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
        <strong>Hinweis zur Spaltenwahl:</strong><br>
        Wenn du bei <strong>Spalten (Erzwingen)</strong> eine Zahl eintragst, wird das Raster fest darauf gesetzt. Lasst du das Feld leer, kann Home Assistant die Kartenbreite wieder flexibel uber das Layout steuern.
      </div>
    `;
  }

  _valueChanged(ev) {
    const config = ev.detail.value;

    if (config.recipes_per_row === "") delete config.recipes_per_row;
    if (config.recipe_count === "") delete config.recipe_count;
    if (typeof config.show_current_week_mealplan !== "boolean") delete config.show_current_week_mealplan;

    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
  }
}
customElements.define("mealie-grocy-card-editor", MealieGrocyCardEditor);

class MealieGrocyCard extends LitElement {
  static get properties() {
    return {
      hass: {},
      config: {},
      _recipePage: { type: Number },
    };
  }

  constructor() {
    super();
    this._recipePage = 0;
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

      .card-stack {
        display: flex;
        flex-direction: column;
        gap: 18px;
      }

      .recipe-section {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .recipe-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 0 4px;
      }

      .recipe-toolbar-info {
        font-size: 0.9rem;
        color: var(--secondary-text-color);
      }

      .recipe-pagination {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .page-indicator {
        min-width: 68px;
        text-align: center;
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }

      .nav-btn {
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.12);
        background: rgba(var(--rgb-primary-text-color), 0.04);
        color: var(--primary-text-color);
        border-radius: 999px;
        padding: 8px 12px;
        cursor: pointer;
        font: inherit;
      }

      .nav-btn[disabled] {
        opacity: 0.45;
        cursor: default;
      }

      .recipe-grid {
        display: grid;
        grid-template-columns: repeat(var(--calculated-columns, 4), minmax(0, 1fr));
        gap: 16px;
        padding: 4px;
        width: 100%;
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
        border: none;
        color: inherit;
        cursor: pointer;
      }

      .recipe-link {
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.82rem;
        font-weight: 600;
      }

      .recipe-card.mini {
        min-height: 240px;
        padding: 12px;
        gap: 8px;
      }

      .recipe-card.mini h3 {
        font-size: 0.9rem;
        -webkit-line-clamp: 1;
      }

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

      .mealplan-section {
        background: rgba(var(--rgb-primary-text-color), 0.03);
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.06);
        border-radius: var(--bubble-border-radius, 20px);
        padding: 16px;
      }

      .mealplan-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
      }

      .mealplan-header h3 {
        margin: 0;
        font-size: 1rem;
      }

      .mealplan-range {
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }

      .mealplan-list {
        display: grid;
        gap: 10px;
      }

      .mealplan-item {
        display: grid;
        grid-template-columns: minmax(110px, 150px) 1fr;
        gap: 10px;
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(var(--rgb-primary-text-color), 0.035);
      }

      .mealplan-day {
        font-weight: 600;
      }

      .mealplan-entry-type {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        margin-top: 4px;
        font-size: 0.75rem;
        color: var(--secondary-text-color);
      }

      .mealplan-empty {
        color: var(--secondary-text-color);
        font-size: 0.9rem;
      }

      @media (max-width: 600px) {
        .recipe-grid {
          grid-template-columns: 1fr !important;
        }

        .recipe-toolbar {
          flex-direction: column;
          align-items: stretch;
        }

        .recipe-pagination {
          justify-content: space-between;
        }

        .page-indicator {
          min-width: auto;
          flex: 1;
        }

        .mealplan-item {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    const entityId = this.config.entity || "sensor.mealie_grocy_kochvorschlage";
    const stateObj = this.hass.states[entityId];

    if (!stateObj || !stateObj.attributes.recipes) {
      return html`<ha-card style="padding: 16px;">Warte auf Daten vom Mealie-Grocy-Sensor...</ha-card>`;
    }

    const allRecipes = stateObj.attributes.recipes || [];
    const recipeLimit = this.config.recipe_count || 4;
    const totalRecipes = allRecipes.length;
    const totalPages = Math.max(1, Math.ceil(totalRecipes / recipeLimit));

    if (this._recipePage >= totalPages) {
      this._recipePage = totalPages - 1;
    }

    const pageStart = this._recipePage * recipeLimit;
    const recipes = allRecipes
      .slice(pageStart, pageStart + recipeLimit)
      .map((recipe, index) => ({ ...recipe, _globalIndex: pageStart + index }));

    const mode = this.config.display_mode || "default";
    const showCurrentWeekMealplan = this.config.show_current_week_mealplan !== false;
    const currentWeekMealplan = stateObj.attributes.current_week_mealplan || [];
    const currentWeekRange = stateObj.attributes.current_week_range || {};

    let calculatedColumns = this.config.recipes_per_row;
    if (!calculatedColumns) {
      const haColumns = this.config.layout?.grid_columns || 12;
      calculatedColumns = haColumns > 4 ? Math.max(1, Math.round(haColumns / 3)) : haColumns;
    }

    return html`
      <ha-card>
        <div class="card-stack">
          <div class="recipe-section">
            ${totalRecipes > recipeLimit ? html`
              <div class="recipe-toolbar">
                <div class="recipe-toolbar-info">
                  Zeige ${pageStart + 1}-${Math.min(pageStart + recipes.length, totalRecipes)} von ${totalRecipes} Rezepten
                </div>
                <div class="recipe-pagination">
                  <button class="nav-btn" ?disabled=${this._recipePage === 0} @click=${this._showPreviousPage}>
                    Zuruck
                  </button>
                  <div class="page-indicator">Seite ${this._recipePage + 1}/${totalPages}</div>
                  <button class="nav-btn" ?disabled=${this._recipePage >= totalPages - 1} @click=${this._showNextPage}>
                    Weiter
                  </button>
                </div>
              </div>
            ` : ""}

            <div class="recipe-grid" style="--calculated-columns: ${calculatedColumns};">
              ${recipes.map((recipe) => {
                const listText = `Rezept ${recipe.recipeName} - ${recipe.matchScore}% - Einkauf ${recipe.missingIngredients.join(", ") || "-"}`;

                return html`
                  <div class="recipe-card ${mode}" data-list-text="${listText}">
                    <div class="title-zone">
                      <h3>${recipe.recipeName} ${recipe.hasExpiring ? "!" : ""}</h3>
                      <div>Score: <strong>${recipe.matchScore}%</strong></div>

                      ${recipe.url ? html`
                        <a class="recipe-link" href="${recipe.url}" target="_blank" rel="noreferrer">
                          Rezept offnen <ha-icon icon="mdi:open-in-new" style="--mdc-icon-size: 14px;"></ha-icon>
                        </a>
                      ` : ""}
                    </div>

                    <div class="content-zone">
                      <div class="ingredient-section">
                        <span class="ingredient-label">Vorhanden:</span>
                        <div class="ingredient-list">
                          ${this._renderMatchingIngredients(recipe.matchingIngredients)}
                        </div>
                      </div>

                      <div class="ingredient-section">
                        <span class="ingredient-label">Basics (ignoriert):</span>
                        <div class="ingredient-list">
                          ${recipe.basicIngredients && recipe.basicIngredients.length > 0
                            ? recipe.basicIngredients.map((i) => this._capitalize(i)).join(", ")
                            : "Keine"}
                        </div>
                      </div>

                      <div class="ingredient-section">
                        <span class="ingredient-label">Einkaufen:</span>
                        <div class="ingredient-list missing">
                          ${recipe.missingIngredients && recipe.missingIngredients.length > 0
                            ? recipe.missingIngredients.map((i) => this._capitalize(i.trim())).join(", ")
                            : "Nichts"}
                        </div>
                      </div>
                    </div>

                    <div class="action-zone">
                      <button class="btn" @click=${() => this._callBridgeService("add_missing_ingredients", recipe._globalIndex)}>
                        <ha-icon icon="mdi:cart-plus"></ha-icon>
                      </button>
                      <button class="btn" @click=${() => this._callBridgeService("set_to_next_free_day", recipe._globalIndex)}>
                        <ha-icon icon="mdi:calendar-plus"></ha-icon>
                      </button>
                    </div>
                  </div>
                `;
              })}
            </div>
          </div>

          ${showCurrentWeekMealplan ? html`
            <div class="mealplan-section">
              <div class="mealplan-header">
                <div>
                  <h3>Aktueller Speiseplan</h3>
                  <div class="mealplan-range">${this._formatWeekRange(currentWeekRange)}</div>
                </div>
              </div>

              ${currentWeekMealplan.length > 0 ? html`
                <div class="mealplan-list">
                  ${currentWeekMealplan.map((entry) => html`
                    <div class="mealplan-item">
                      <div>
                        <div class="mealplan-day">${this._formatMealplanDate(entry)}</div>
                        <div class="mealplan-entry-type">${this._formatEntryType(entry.entryType)}</div>
                      </div>
                      <div>${entry.recipeName}</div>
                    </div>
                  `)}
                </div>
              ` : html`
                <div class="mealplan-empty">Fur diese Samstag-bis-Samstag-Woche sind aktuell keine Eintrage vorhanden.</div>
              `}
            </div>
          ` : ""}
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
      display_mode: "default",
      show_current_week_mealplan: true,
    };
  }

  setConfig(config) {
    this.config = config;
    this._recipePage = 0;
  }

  getCardSize() {
    return 4;
  }

  _callBridgeService(serviceName, index) {
    this.hass.callService("mealie_grocy_bridge", serviceName, {
      recipe_index: index,
    });
  }

  _showPreviousPage = () => {
    if (this._recipePage > 0) {
      this._recipePage -= 1;
    }
  };

  _showNextPage = () => {
    const totalRecipes = this.hass?.states?.[this.config?.entity || "sensor.mealie_grocy_kochvorschlage"]?.attributes?.recipes?.length || 0;
    const recipeLimit = this.config?.recipe_count || 4;
    const totalPages = Math.max(1, Math.ceil(totalRecipes / recipeLimit));
    if (this._recipePage < totalPages - 1) {
      this._recipePage += 1;
    }
  };

  _renderMatchingIngredients(ingredients) {
    if (!ingredients || ingredients.length === 0) {
      return "Keine";
    }

    return ingredients.map((ingredient, index) => {
      const name = this._capitalize(ingredient.name || "Unbekannt");
      let content = html`${name}`;

      if (ingredient.status === "expired") {
        content = html`<span class="expired">${name}</span>`;
      } else if (ingredient.status === "expiring") {
        content = html`<span class="expiring">${name}</span>`;
      }

      return html`${index > 0 ? ", " : ""}${content}`;
    });
  }

  _capitalize(value) {
    if (!value) return "";
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  _formatMealplanDate(entry) {
    const dateValue = entry?.date;
    if (!dateValue) {
      return entry?.dateLabel || "Ohne Datum";
    }
    const date = new Date(`${dateValue}T12:00:00`);
    return new Intl.DateTimeFormat("de-DE", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
    }).format(date);
  }

  _formatWeekRange(range) {
    if (!range?.start || !range?.end) {
      return "Samstag bis Samstag";
    }
    const start = new Date(`${range.start}T12:00:00`);
    const end = new Date(`${range.end}T12:00:00`);
    const formatter = new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    return `${formatter.format(start)} bis ${formatter.format(end)}`;
  }

  _formatEntryType(entryType) {
    const mapping = {
      breakfast: "Fruhstuck",
      lunch: "Mittagessen",
      dinner: "Abendessen",
      side: "Beilage",
      snack: "Snack",
      dessert: "Dessert",
      meal: "Mahlzeit",
    };
    return mapping[entryType] || entryType || "Eintrag";
  }
}

customElements.define("mealie-grocy-card", MealieGrocyCard);

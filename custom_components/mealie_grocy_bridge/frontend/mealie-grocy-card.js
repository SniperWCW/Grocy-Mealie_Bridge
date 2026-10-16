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
      { name: "entity", label: "Sensor Entität", selector: { entity: { domain: "sensor" } } },
      {
        name: "display_mode",
        label: "Darstellung",
        selector: {
          select: {
            options: [
              { value: "default", label: "Standard - Vollansicht" },
              { value: "mini", label: "Mini - kompakter, weniger Höhe" },
              { value: "compact", label: "Kompakt - sehr platzsparend, ideal für 4-6 Spalten" },
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
        Wenn du bei <strong>Spalten (Erzwingen)</strong> eine Zahl eintragst, wird das Raster fest darauf gesetzt. Lässt du das Feld leer, kann Home Assistant die Kartenbreite wieder flexibel über das Layout steuern.
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
if (!customElements.get("mealie-grocy-card-editor")) {
  customElements.define("mealie-grocy-card-editor", MealieGrocyCardEditor);
}

class MealieGrocyCard extends LitElement {
  static get properties() {
    return {
      hass: {},
      config: {},
      _recipePage: { type: Number },
      _scheduleOptions: { type: Object },
    };
  }

  constructor() {
    super();
    this._recipePage = 0;
    this._scheduleOptions = {};
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

      .recipe-title-row,
      .score-line,
      .section-label,
      .schedule-label {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .recipe-status-flag {
        font-size: 1.2rem;
        line-height: 1;
      }

      .score-line {
        font-size: 1.02rem;
        margin-bottom: 4px;
      }

      .section-icon,
      .score-icon,
      .schedule-icon {
        color: var(--primary-color);
        --mdc-icon-size: 18px;
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

      .ingredient-list {
        line-height: 1.6;
      }

      .expired {
        color: #ff5252;
        background: rgba(255, 82, 82, 0.12);
        border-radius: 999px;
        padding: 1px 8px;
        font-weight: bold;
      }

      .expiring {
        color: orange;
        background: rgba(255, 165, 0, 0.14);
        border-radius: 999px;
        padding: 1px 8px;
        font-weight: bold;
      }

      .missing {
        opacity: 0.85;
      }

      .action-zone {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 12px;
        border-top: 1px solid rgba(var(--rgb-primary-text-color), 0.08);
        padding-top: 12px;
      }

      .schedule-zone {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .schedule-controls {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: 8px;
      }

      .schedule-date {
        width: 100%;
        box-sizing: border-box;
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.12);
        background: rgba(var(--rgb-primary-text-color), 0.03);
        color: var(--primary-text-color);
        border-radius: 12px;
        padding: 8px 10px;
        font: inherit;
      }

      .meal-type-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }

      .meal-type-btn {
        border: 1px solid rgba(var(--rgb-primary-text-color), 0.12);
        background: rgba(var(--rgb-primary-text-color), 0.03);
        color: var(--primary-text-color);
        border-radius: 999px;
        padding: 6px 10px;
        cursor: pointer;
        font: inherit;
        font-size: 0.78rem;
      }

      .meal-type-btn.active {
        background: rgba(var(--rgb-primary-color), 0.18);
        border-color: rgba(var(--rgb-primary-color), 0.35);
      }

      .action-buttons {
        display: flex;
        justify-content: center;
        gap: 24px;
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
        box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
      }

      .btn-shopping {
        color: #00a4d8;
      }

      .btn-calendar {
        color: #d99a49;
      }

      .recipe-link {
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.82rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
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

      .recipe-card.compact .meal-type-btn {
        padding: 4px 8px;
        font-size: 0.68rem;
      }

      .recipe-card.compact .schedule-date {
        padding: 6px 8px;
        font-size: 0.72rem;
      }

      .recipe-card.compact .btn {
        width: 28px;
        height: 28px;
      }

      .recipe-card.compact .section-icon,
      .recipe-card.compact .score-icon,
      .recipe-card.compact .schedule-icon {
        --mdc-icon-size: 15px;
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
        grid-template-columns: minmax(110px, 150px) minmax(0, 1fr);
        gap: 12px;
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

      .mealplan-content {
        display: grid;
        grid-template-columns: 72px minmax(0, 1fr);
        gap: 12px;
        align-items: center;
        min-width: 0;
      }

      .mealplan-content.no-thumb {
        grid-template-columns: minmax(0, 1fr);
      }

      .mealplan-thumb {
        width: 72px;
        height: 72px;
        object-fit: cover;
        border-radius: 12px;
        background: rgba(var(--rgb-primary-text-color), 0.06);
      }

      .mealplan-text {
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .mealplan-recipe-name {
        font-weight: 600;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }

      .mealplan-times {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }

      .mealplan-time-pill {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(var(--rgb-primary-text-color), 0.05);
        color: var(--secondary-text-color);
        font-size: 0.75rem;
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

        .mealplan-content {
          grid-template-columns: 56px minmax(0, 1fr);
        }

        .mealplan-content.no-thumb {
          grid-template-columns: minmax(0, 1fr);
        }

        .mealplan-thumb {
          width: 56px;
          height: 56px;
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
    const currentWeekMealplan = stateObj.attributes.mealplan || stateObj.attributes.current_week_mealplan || [];
    const currentWeekRange = stateObj.attributes.mealplan_range || stateObj.attributes.current_week_range || {};

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
                    Zurück
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
                      <div class="recipe-title-row">
                        <ha-icon class="section-icon" icon="mdi:food"></ha-icon>
                        <h3>${recipe.recipeName}</h3>
                        ${recipe.hasExpiring ? html`<span class="recipe-status-flag" title="Mindestens eine vorhandene Zutat ist abgelaufen oder läuft bald ab">🔥</span>` : ""}
                      </div>
                      <div class="score-line">
                        <ha-icon class="score-icon" icon="mdi:chart-bar"></ha-icon>
                        <span>Score: <strong>${recipe.matchScore}%</strong></span>
                      </div>

                      ${recipe.url ? html`
                        <a class="recipe-link" href="${recipe.url}" target="_blank" rel="noreferrer">
                          <span>👉 Rezept öffnen</span>
                          <ha-icon icon="mdi:open-in-new" style="--mdc-icon-size: 14px;"></ha-icon>
                        </a>
                      ` : ""}
                    </div>

                    <div class="content-zone">
                      <div class="ingredient-section">
                        <span class="ingredient-label section-label">
                          <span>✅</span>
                          <span>Vorhanden:</span>
                        </span>
                        <div class="ingredient-list">
                          ${this._renderMatchingIngredients(recipe.matchingIngredients)}
                        </div>
                      </div>

                      <div class="ingredient-section">
                        <span class="ingredient-label section-label">
                          <span>🧂</span>
                          <span>Basics (ignoriert):</span>
                        </span>
                        <div class="ingredient-list">
                          ${recipe.basicIngredients && recipe.basicIngredients.length > 0
                            ? recipe.basicIngredients.map((i) => this._capitalize(i)).join(", ")
                            : "Keine"}
                        </div>
                      </div>

                      <div class="ingredient-section">
                        <span class="ingredient-label section-label">
                          <span>🛒</span>
                          <span>Einkaufen:</span>
                        </span>
                        <div class="ingredient-list missing">
                          ${recipe.missingIngredients && recipe.missingIngredients.length > 0
                            ? recipe.missingIngredients.map((i) => this._capitalize(i.trim())).join(", ")
                            : "Nichts"}
                        </div>
                      </div>
                    </div>

                    <div class="action-zone">
                      <div class="schedule-zone">
                        <div class="ingredient-label schedule-label">
                          <ha-icon class="schedule-icon" icon="mdi:calendar-month"></ha-icon>
                          <span>Datum wählen:</span>
                        </div>
                        <div class="schedule-controls">
                          <input
                            class="schedule-date"
                            type="date"
                            .value=${this._getScheduleOption(recipe._globalIndex).date}
                            @change=${(event) => this._updateScheduleDate(recipe._globalIndex, event)}
                          >
                          <div class="meal-type-row">
                            ${this._mealTypes().map((mealType) => html`
                              <button
                                type="button"
                                class="meal-type-btn ${this._getScheduleOption(recipe._globalIndex).entryType === mealType.value ? "active" : ""}"
                                @click=${() => this._updateScheduleType(recipe._globalIndex, mealType.value)}
                              >
                                <ha-icon icon="${mealType.icon}" style="--mdc-icon-size: 14px; margin-right: 4px;"></ha-icon>
                                ${mealType.label}
                              </button>
                            `)}
                          </div>
                        </div>
                      </div>

                      <div class="action-buttons">
                        <button type="button" class="btn btn-shopping" title="Zur Einkaufsliste hinzufügen" @click=${() => this._callBridgeService("add_missing_ingredients", recipe._globalIndex, recipe.recipeId)}>
                          <ha-icon icon="mdi:cart-plus"></ha-icon>
                        </button>
                        <button type="button" class="btn btn-calendar" title="Zum Speiseplan hinzufügen" @click=${() => this._callBridgeService("set_to_next_free_day", recipe._globalIndex, recipe.recipeId)}>
                          <ha-icon icon="mdi:calendar-plus"></ha-icon>
                        </button>
                      </div>
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
                  <h3>Speiseplan</h3>
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
                      <div class="mealplan-content ${entry.imageUrl ? "" : "no-thumb"}">
                        ${entry.imageUrl ? html`
                          <img
                            class="mealplan-thumb"
                            src="${entry.imageUrl}"
                            data-fallback-src="${entry.imageFallbackUrl || ""}"
                            alt="${entry.recipeName}"
                            loading="lazy"
                            @error=${this._handleMealplanImageError}
                          >
                        ` : ""}
                        <div class="mealplan-text">
                          <div class="mealplan-recipe-name">${entry.recipeName}</div>
                          ${this._renderMealplanTimes(entry)}
                        </div>
                      </div>
                    </div>
                  `)}
                </div>
              ` : html`
                <div class="mealplan-empty">Für den gewählten Zeitraum sind aktuell keine Einträge vorhanden.</div>
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
    this._scheduleOptions = {};
  }

  getCardSize() {
    return 4;
  }

  _callBridgeService(serviceName, index, recipeId) {
    // Prefer the stable recipe id captured at render time; the index is only a
    // fallback because the sensor order can change before the click.
    const payload = recipeId ? { recipe_id: String(recipeId) } : { recipe_index: index };

    if (serviceName === "set_to_next_free_day") {
      const scheduleOption = this._getScheduleOption(index);
      if (scheduleOption.date) {
        payload.selected_date = scheduleOption.date;
      }
      payload.entry_type = scheduleOption.entryType;
    }

    this.hass.callService("mealie_grocy_bridge", serviceName, payload);
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

  _getScheduleOption(index) {
    return this._scheduleOptions[index] || { date: "", entryType: "dinner" };
  }

  _updateScheduleDate(index, event) {
    this._scheduleOptions = {
      ...this._scheduleOptions,
      [index]: {
        ...this._getScheduleOption(index),
        date: event.target.value || "",
      },
    };
  }

  _updateScheduleType(index, entryType) {
    this._scheduleOptions = {
      ...this._scheduleOptions,
      [index]: {
        ...this._getScheduleOption(index),
        entryType,
      },
    };
  }

  _mealTypes() {
    return [
      { value: "breakfast", label: "Frühstück", icon: "mdi:coffee" },
      { value: "lunch", label: "Mittagessen", icon: "mdi:white-balance-sunny" },
      { value: "dinner", label: "Abendessen", icon: "mdi:weather-night" },
    ];
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
      return "Kein Zeitraum";
    }
    const start = new Date(`${range.start}T12:00:00`);
    const end = new Date(`${range.end}T12:00:00`);
    const formatter = new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const label = range?.label ? `${range.label}: ` : "";
    return `${label}${formatter.format(start)} bis ${formatter.format(end)}`;
  }

  _formatEntryType(entryType) {
    const mapping = {
      breakfast: "Frühstück",
      lunch: "Mittagessen",
      dinner: "Abendessen",
      side: "Beilage",
      snack: "Snack",
      dessert: "Dessert",
      meal: "Mahlzeit",
    };
    return mapping[entryType] || entryType || "Eintrag";
  }

  _renderMealplanTimes(entry) {
    const timeItems = [
      entry?.prepTime ? { label: "Vorb.", value: entry.prepTime } : null,
      entry?.cookTime ? { label: "Koch.", value: entry.cookTime } : null,
      entry?.totalTime ? { label: "Gesamt", value: entry.totalTime } : null,
    ].filter(Boolean);

    if (timeItems.length === 0) {
      return "";
    }

    return html`
      <div class="mealplan-times">
        ${timeItems.map((item) => html`
          <div class="mealplan-time-pill">${item.label}: ${item.value}</div>
        `)}
      </div>
    `;
  }

  _handleMealplanImageError = (event) => {
    const image = event?.target;
    if (image) {
      const fallbackSrc = image.dataset?.fallbackSrc;
      if (fallbackSrc && image.src !== fallbackSrc) {
        image.src = fallbackSrc;
        image.dataset.fallbackSrc = "";
        return;
      }
      image.style.display = "none";
    }
  };
}

if (!customElements.get("mealie-grocy-card")) {
  customElements.define("mealie-grocy-card", MealieGrocyCard);
}

const EMERGENCY_SOURCE_URL = "https://www.ernaehrungsvorsorge.de/private-vorsorge/notvorrat/vorratskalkulator";
const DEFAULT_CHILD_FOOD_FACTOR = 0.7;
const DEFAULT_KCAL_PER_ADULT = 2200; // BLE/DGE-Richtwert für den Notvorrat, Kinder wie bei den Mengen mit 70 %
const DEFAULT_CHILD_DRINK_LITERS_PER_DAY = 1;
const OIL_DENSITY = 0.92;

// Reihenfolge = Priorität: passt ein Produkt auf mehrere Gruppen, zählt es nur in der ersten.
// Suchbegriffe sind normalisiert (klein, ohne Umlaute, ß = ss). Bis 2 Zeichen zählt nur das
// ganze Wort, 3 Zeichen der Wortanfang, ab 4 Zeichen auch ein Wortteil ("Glasnudeln" → "nudel").
const EMERGENCY_CATEGORIES = [
  {
    id: "grain",
    title: "Getreide, Brot, Kartoffeln",
    icon: "mdi:bread-slice-outline",
    measurement: "grams",
    adultDailyTarget: 330,
    alternatives: ["Vollkornbrot", "Knäckebrot", "Zwieback", "Reis", "Nudeln", "Haferflocken", "Kartoffeln"],
    keywords: [
      "brot", "zwieback", "reis", "nudel", "noodle", "ramen", "ramyun", "udon", "chapaghetti",
      "spaghetti", "fusilli", "farfalle", "penne", "tortiglioni", "lasagne", "spatzle", "spaetzle",
      "gnocchi", "hafer", "getreide", "muesli", "musli", "griess", "semola", "mehl", "couscous",
      "bulgur", "quinoa", "polenta", "graupen", "kartoffel",
    ],
  },
  {
    id: "vegetables",
    title: "Gemüse und Hülsenfrüchte",
    icon: "mdi:carrot",
    measurement: "grams",
    adultDailyTarget: 400,
    alternatives: ["Tomaten", "Erbsen", "Mais", "Karotten", "Sauerkraut", "Linsen", "Bohnen"],
    keywords: [
      "gemuse", "gemuese", "tomat", "passata", "erbs", "mais", "bohn", "linse", "karott", "mohre",
      "paprika", "gurk", "zucchini", "sauerkraut", "rotkohl", "rotkraut", "pilz", "champignon",
      "kichererb", "spinat", "mangold", "brokkoli", "blumenkohl", "kohlrabi", "eintopf",
    ],
  },
  {
    id: "fruit",
    title: "Obst, Nüsse",
    icon: "mdi:fruit-cherries",
    measurement: "grams",
    adultDailyTarget: 250,
    alternatives: ["Apfelmus", "Trockenobst", "Birnen", "Pfirsiche", "Rosinen", "Nüsse"],
    keywords: [
      "obst", "apfel", "birn", "pfirs", "aprik", "mandarin", "orange", "ananas", "beere", "rosin",
      "pflaum", "mango", "banan", "kirsch", "nuss", "nusse", "mandel", "cashew", "pistazie",
    ],
  },
  {
    id: "milk",
    title: "Milch und Milchprodukte",
    icon: "mdi:cow",
    measurement: "grams",
    adultDailyTarget: 260,
    alternatives: ["H-Milch", "Joghurt", "Hartkäse", "Kondensmilch", "Pflanzendrinks"],
    keywords: [
      "milch", "joghurt", "kase", "quark", "skyr", "kefir", "sahne", "mozzarella", "mozarella",
      "feta", "pflanzendrink", "haferdrink", "sojadrink",
    ],
  },
  {
    id: "protein",
    title: "Fleisch, Fisch, Eier, Ersatz",
    icon: "mdi:food-drumstick-outline",
    measurement: "grams",
    adultDailyTarget: 120,
    alternatives: ["Fischkonserven", "Wurst", "Eier", "Tofu", "Lupinen", "Veggie-Ersatz"],
    keywords: [
      "fleisch", "fisch", "ei", "eier", "wurst", "wiener", "schinken", "thunfisch", "makrele",
      "sardine", "huhn", "hahnchen", "chicken", "nugget", "pute", "rind", "schwein", "beef",
      "corned", "gulasch", "hack", "salami", "frikadell", "schnitzel", "terrine", "garnele",
      "prawn", "muschel", "tofu", "tempeh", "lupine", "seitan", "protein",
    ],
  },
  {
    id: "fats",
    title: "Fette und Öle",
    icon: "mdi:bottle-tonic-plus-outline",
    measurement: "grams",
    adultDailyTarget: 35,
    alternatives: ["Olivenöl", "Sonnenblumenöl", "Rapsöl", "Butter", "Margarine", "Nussmus"],
    keywords: [
      "ol", "oel", "olivenol", "rapsol", "sonnenblumenol", "speiseol", "kokosol", "butter",
      "margarine", "schmalz", "ghee", "nussmus",
    ],
  },
  {
    id: "drinks",
    title: "Getränke",
    icon: "mdi:cup-water",
    measurement: "liters",
    adultDailyTarget: 2,
    childDailyTarget: DEFAULT_CHILD_DRINK_LITERS_PER_DAY,
    alternatives: ["Mineralwasser", "Saft", "Tee", "Kaffee", "Haltbare Schorlen"],
    keywords: ["wasser", "saft", "nektar", "cola", "limonade", "schorle", "getrank", "sirup"],
  },
];

const EMERGENCY_CATEGORY_IDS = EMERGENCY_CATEGORIES.map((category) => category.id);
const EMERGENCY_IGNORE_IDS = ["none", "ignore", "keine", "ignorieren"];

// Feste Regeln vor der Suchbegriff-Zuordnung, erste Regel gewinnt. category: null = zählt nie.
// Geprüft wird der normalisierte Produktname.
const EMERGENCY_RULES = [
  // Haushalt und Drogerie
  { pattern: /(reinig|spray|seife|tabs|spuler|spulmittel|pfleger|putzmittel|schimmel|backpapier|natron|zitronensaure|lebensmittelfarbe)/, category: null },
  // Gemüseprodukte, die sonst an "sosse" oder "essig" hängen bleiben
  { pattern: /(tomatensosse|tomatensauce|passierte tomaten|tomaten gehackt|gehackte tomaten|tomatenmark|paprikamark|essiggurk|gewurzgurk)/, category: "vegetables" },
  // Fisch im eigenen Saft ist kein Getränk
  { pattern: /(thunfisch|makrele|sardine|fischfilet)/, category: "protein" },
  // Mehrdeutige Namen, die sonst in der falschen Gruppe landen
  { pattern: /(haferdrink|hafermilch|sojadrink|mandeldrink|pflanzendrink)/, category: "milk" },
  { pattern: /(nussmus|erdnussbutter)/, category: "fats" },
  { pattern: /preiselbeer/, category: "fruit" },
  { pattern: /(saft|nektar|schorle)\b/, category: "drinks" },
  // Würzmittel, Saucen, Backzutaten, Süßes, Snacks, Kaffee – laut BLE kein Teil der Grundgruppen
  { pattern: /(sauce|sosse|senf|pesto|ketchup|mayo|dressing|gewurz|\brub\b|maggi|bruhe|fond|bouillon|paste|sriracha|chilli|chili|essig|salz\b|pfeffer|zucker\b|backpulver|starke\b|schoko|tropfchen|creme|chips|snack|croki|\bpico\b|picco|apero|truffel|kaffee|kokosmilch|\btee\b|pancake)/, category: null },
  // Oliven sind kein Speiseöl
  { pattern: /\boliven?\b(?! ?ol)/, category: null },
];

// Produktgruppen aus Grocy, die ohne Konfiguration erkannt werden (normalisierter Gruppenname).
const EMERGENCY_GROUP_DEFAULTS = [
  { pattern: /(reinig|haushalt|drogerie|hygiene|kosmetik|tierbedarf)/, category: null },
  { pattern: /(gewurz|sossen|saucen|snack|sussigkeit|susswaren|backzutat|kaffee)/, category: null },
  { pattern: /(nudel|teigwar|getreide|reis|mehl|brot|backwar|kartoffel)/, category: "grain" },
  { pattern: /(gemuse|hulsenfrucht)/, category: "vegetables" },
  { pattern: /(obst|nuss|nusse|trockenfrucht)/, category: "fruit" },
  { pattern: /(milch|molkerei|kase)/, category: "milk" },
  { pattern: /(fleisch|fisch|wurst|eier|meeresfrucht)/, category: "protein" },
  { pattern: /\b(ol|ole|oel|oele|fett|fette)\b/, category: "fats" },
  { pattern: /(getrank|wasser|saft)/, category: "drinks" },
];

// Typische Packungsgrößen für Artikel in "Stück" oder ohne Einheit. Erste passende Zeile gewinnt.
const EMERGENCY_UNITLESS_ESTIMATES = {
  grain: [
    { pattern: /paniermehl/, grams: 400 },
    { pattern: /mehl/, grams: 1000 },
    { pattern: /(express reis|reis mediterran|djuvec)/, grams: 250 },
    { pattern: /(ramen|ramyun|yumyum|yum yum|chapaghetti|neoguri|jjajang|asia nudeln|instant)/, grams: 75 },
    { pattern: /udon/, grams: 200 },
    { pattern: /wan tan/, grams: 250 },
    { pattern: /kartoffelpuree|kartoffelbrei/, grams: 250 },
    { pattern: /kartoffel/, grams: 1000 },
    { pattern: /(reis|graupen|griess|hafer|getreide|muesli|musli|semola|couscous|bulgur|quinoa|polenta)/, grams: 500 },
    { pattern: /(nudel|noodle|spaghetti|fusilli|farfalle|penne|tortiglioni|lasagne|spatzle|spaetzle|gnocchi)/, grams: 500 },
    { pattern: /(brot|zwieback)/, grams: 250 },
  ],
  vegetables: [
    { pattern: /(tomatenmark|paprikamark)/, grams: 200 },
    { pattern: /(passierte tomaten|tomaten gehackt|gehackte tomaten|tomatensosse|tomatensauce|passata)/, grams: 400 },
    { pattern: /linse/, grams: 500 },
    { pattern: /gurk/, grams: 300 },
  ],
  fruit: [
    { pattern: /apfelmus/, grams: 360 },
    { pattern: /(mandarin|orange|pfirs|aprik|ananas|kirsch)/, grams: 300 },
    { pattern: /(nuss|mandel|cashew|pistazie)/, grams: 200 },
  ],
  milk: [
    { pattern: /kondensmilch/, grams: 170 },
    { pattern: /milch/, grams: 1000 },
    { pattern: /sahne/, grams: 200 },
    { pattern: /kase/, grams: 200 },
  ],
  protein: [
    { pattern: /\beier?\b/, grams: 53 },
    { pattern: /(thunfisch|makrele|sardine|fischfilet|corned beef|terrine)/, grams: 180 },
    { pattern: /(tofu|tempeh|protein)/, grams: 200 },
  ],
  fats: [
    { pattern: /(butter|margarine|schmalz)/, grams: 250 },
    { pattern: /(ol|oel)\b/, grams: 500 },
  ],
  drinks: [
    { pattern: /wasser/, liters: 1.5 },
    { pattern: /(saft|nektar|cola|limonade|schorle|getrank)/, liters: 1 },
  ],
};

// Rückfall, wenn keine Zeile oben passt (Liter-Gruppen schätzen nie).
const EMERGENCY_FALLBACK_GRAMS = {
  grain: 500,
  vegetables: 400,
  fruit: 250,
  milk: 250,
  protein: 250,
  fats: 500,
};

function normalizeEmergencyText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function matchesEmergencyKeyword(tokens, keyword) {
  if (keyword.length <= 2) return tokens.some((token) => token === keyword);
  if (keyword.length === 3) return tokens.some((token) => token.startsWith(keyword));
  return tokens.some((token) => token.includes(keyword));
}

class MealieGrocyEmergencyCardEditor extends LitElement {
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
      { name: "entity", label: "Sensor Entität", selector: { entity: { domain: "sensor" } } },
      {
        name: "",
        type: "grid",
        column_min_width: "100px",
        schema: [
          { name: "adults", label: "Erwachsene", selector: { number: { min: 1, max: 20, mode: "box" } } },
          { name: "children", label: "Kinder", selector: { number: { min: 0, max: 20, mode: "box" } } },
          { name: "days", label: "Tage", selector: { number: { min: 1, max: 60, mode: "box" } } },
          { name: "water_liters", label: "Wasser extern (Liter)", selector: { number: { min: 0, max: 1000, step: 0.5, mode: "box" } } },
          { name: "kcal_per_adult", label: "kcal je Erwachsener und Tag", selector: { number: { min: 1000, max: 4000, step: 50, mode: "box" } } },
          { name: "collapsible", label: "Ein-/ausblendbar", selector: { boolean: {} } },
          { name: "initially_collapsed", label: "Initial eingeklappt", selector: { boolean: {} } },
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
        Kinder werden standardmäßig mit 70% des Erwachsenenbedarfs berechnet.
        Für Getränke wird 1 Liter pro Kind und Tag angesetzt.
        „Wasser extern“ zählt Getränke mit, die nicht in Grocy erfasst sind.
        Grocy-Produktgruppen lassen sich per YAML mit <code>product_groups</code> einer Gruppe zuordnen.
      </div>
    `;
  }

  _valueChanged(ev) {
    const config = { ...ev.detail.value };

    ["adults", "children", "days", "water_liters", "kcal_per_adult"].forEach((key) => {
      if (config[key] === "") delete config[key];
    });
    if (typeof config.collapsible !== "boolean") delete config.collapsible;
    if (typeof config.initially_collapsed !== "boolean") delete config.initially_collapsed;

    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
  }
}
if (!customElements.get("mealie-grocy-emergency-card-editor")) {
  customElements.define("mealie-grocy-emergency-card-editor", MealieGrocyEmergencyCardEditor);
}

class MealieGrocyEmergencyCard extends LitElement {
  static get properties() {
    return {
      hass: {},
      config: {},
      _collapsed: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._collapsed = false;
  }

  static getConfigElement() {
    return document.createElement("mealie-grocy-emergency-card-editor");
  }

  static get styles() {
    return css`
      :host {
        display: block;
        width: 100%;
      }

      ha-card {
        padding: 20px;
        border-radius: 24px;
        background:
          radial-gradient(circle at top right, rgba(90, 157, 109, 0.18), transparent 34%),
          linear-gradient(145deg, rgba(34, 53, 43, 0.96), rgba(24, 32, 28, 0.98));
        color: #f3f1e8;
        overflow: hidden;
      }

      .stack {
        display: flex;
        flex-direction: column;
        gap: 18px;
      }

      .hero {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr);
        gap: 16px;
        align-items: stretch;
      }

      .hero-topline {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
      }

      .hero-copy {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }

      .eyebrow {
        display: inline-flex;
        width: fit-content;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(243, 241, 232, 0.1);
        color: rgba(243, 241, 232, 0.92);
        font-size: 0.78rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }

      .hero h2 {
        margin: 0;
        font-size: 1.45rem;
        line-height: 1.15;
      }

      .hero p {
        margin: 0;
        color: rgba(243, 241, 232, 0.78);
        line-height: 1.45;
      }

      .toggle-btn {
        flex: none;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 1px solid rgba(243, 241, 232, 0.12);
        background: rgba(243, 241, 232, 0.08);
        color: #f3f1e8;
        border-radius: 999px;
        padding: 8px 12px;
        cursor: pointer;
        font: inherit;
      }

      .hero-stats {
        display: grid;
        gap: 12px;
      }

      .hero-stat {
        padding: 14px 16px;
        border-radius: 18px;
        background: rgba(243, 241, 232, 0.08);
        border: 1px solid rgba(243, 241, 232, 0.08);
      }

      .hero-stat-label {
        display: block;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: rgba(243, 241, 232, 0.68);
        margin-bottom: 6px;
      }

      .hero-stat-value {
        font-size: 1.5rem;
        font-weight: 700;
      }

      .hero-stat-sub {
        margin-top: 4px;
        color: rgba(243, 241, 232, 0.68);
        font-size: 0.86rem;
      }

      .hero-stat-warning {
        margin-top: 8px;
        color: #ffb3b3;
        font-size: 0.8rem;
        line-height: 1.35;
      }

      .category-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
        gap: 14px;
      }

      .category-card {
        padding: 16px;
        border-radius: 20px;
        background: rgba(248, 246, 239, 0.08);
        border: 1px solid rgba(248, 246, 239, 0.08);
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .category-head,
      .category-foot,
      .chip-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
      }

      .category-title {
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: 0;
      }

      .category-title-text {
        font-weight: 600;
        line-height: 1.2;
      }

      .category-icon {
        color: #d6ebb4;
        --mdc-icon-size: 22px;
      }

      .score-pill {
        flex: none;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 0.85rem;
        font-weight: 700;
        background: rgba(214, 235, 180, 0.18);
        color: #edf7d8;
      }

      .score-pill.low {
        background: rgba(255, 193, 118, 0.18);
        color: #ffd7a3;
      }

      .score-pill.critical {
        background: rgba(255, 121, 121, 0.18);
        color: #ffb3b3;
      }

      .progress-rail {
        width: 100%;
        height: 10px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(243, 241, 232, 0.08);
      }

      .progress-fill {
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #9ecb72, #e4f2a1);
      }

      .progress-fill.low {
        background: linear-gradient(90deg, #d49d57, #f3d28e);
      }

      .progress-fill.critical {
        background: linear-gradient(90deg, #c85d5d, #f0a4a4);
      }

      .meta {
        color: rgba(243, 241, 232, 0.72);
        font-size: 0.86rem;
        line-height: 1.4;
      }

      .meta.alert {
        color: #ffb3b3;
        font-weight: 600;
      }

      .chip-row {
        justify-content: flex-start;
        flex-wrap: wrap;
      }

      .chip {
        border-radius: 999px;
        padding: 5px 9px;
        background: rgba(243, 241, 232, 0.08);
        color: rgba(243, 241, 232, 0.82);
        font-size: 0.75rem;
      }

      .matched-list {
        color: rgba(243, 241, 232, 0.88);
        font-size: 0.82rem;
        line-height: 1.45;
      }

      .footer-note {
        color: rgba(243, 241, 232, 0.68);
        font-size: 0.8rem;
        line-height: 1.45;
      }

      .footer-note a {
        color: #d6ebb4;
      }

      .card-version {
        margin-top: 6px;
        color: rgba(243, 241, 232, 0.5);
        font-size: 0.74rem;
      }

      @media (max-width: 700px) {
        .hero {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_vorrat",
      adults: 2,
      children: 0,
      days: 10,
      collapsible: true,
      initially_collapsed: false,
    };
  }

  setConfig(config) {
    this.config = config;
    this._collapsed = Boolean(config.initially_collapsed);
  }

  getCardSize() {
    return 4;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    let entityId = this.config.entity || "sensor.mealie_grocy_vorrat";
    let stateObj = this.hass.states[entityId];

    // Existing dashboards may still point to the former combined sensor.
    if (!stateObj?.attributes?.stock_items && entityId === "sensor.mealie_grocy_kochvorschlage") {
      entityId = "sensor.mealie_grocy_vorrat";
      stateObj = this.hass.states[entityId];
    }

    if (!stateObj || !stateObj.attributes?.stock_items) {
      return html`<ha-card>Warte auf Grocy-Bestandsdaten...</ha-card>`;
    }

    const adults = this._toPositiveInt(this.config.adults, 2);
    const children = this._toPositiveInt(this.config.children, 0, true);
    const days = this._toPositiveInt(this.config.days, 10);
    const waterLiters = this._toNonNegativeNumber(this.config.water_liters);
    const kcalPerAdult = this._toPositiveInt(this.config.kcal_per_adult, DEFAULT_KCAL_PER_ADULT);
    const collapsible = this.config.collapsible !== false;
    const stockItems = stateObj.attributes.stock_items || [];
    const summary = this._buildSummary(stockItems, adults, children, days, waterLiters, kcalPerAdult);
    const integrationVersion = stateObj.attributes.integration_version || "unbekannt";
    const overallCoverage = this._formatOverallCoverage(summary, days);

    return html`
      <ha-card>
        <div class="stack">
          <div class="hero">
            <div class="hero-copy">
              <div class="hero-topline">
                <div class="eyebrow">
                  <ha-icon icon="mdi:shield-check-outline"></ha-icon>
                  <span>Krisenvorsorge</span>
                </div>
                ${collapsible ? html`
                  <button type="button" class="toggle-btn" @click=${this._toggleCollapsed}>
                    <ha-icon icon="${this._collapsed ? "mdi:eye-outline" : "mdi:eye-off-outline"}"></ha-icon>
                    <span>${this._collapsed ? "Einblenden" : "Ausblenden"}</span>
                  </button>
                ` : ""}
              </div>
              <h2>Notvorrat für ${adults} Erwachsene, ${children} Kinder und ${days} Tage</h2>
              <p>
                Die Bewertung basiert auf den BLE-Richtwerten pro Tag und erwachsene Person.
                Kinder werden mit 70% angesetzt, Getränke mit 1 Liter pro Kind und Tag.
              </p>
            </div>

            <div class="hero-stats">
              <div class="hero-stat">
                <span class="hero-stat-label">Notvorrat reicht für</span>
                <div class="hero-stat-value">${overallCoverage.label}</div>
                <div class="hero-stat-sub">${overallCoverage.detail}</div>
                ${summary.zeroCategories.length > 0 ? html`
                  <div class="hero-stat-warning">
                    Kein Vorrat erkannt bei: ${summary.zeroCategories.map((category) => category.title).join(", ")}
                  </div>
                ` : ""}
              </div>
              <div class="hero-stat">
                <span class="hero-stat-label">Kalorien reichen für</span>
                <div class="hero-stat-value">${summary.kcal.label}</div>
                <div class="hero-stat-sub">${summary.kcal.detail}</div>
                ${summary.kcal.warning ? html`<div class="hero-stat-warning">${summary.kcal.warning}</div>` : ""}
              </div>
              <div class="hero-stat">
                <span class="hero-stat-label">Gruppen im Ziel</span>
                <div class="hero-stat-value">${summary.categoriesAtTarget}/${summary.categories.length}</div>
                <div class="hero-stat-sub">${summary.lowestCategory.title}: ${summary.lowestCategory.scoreLabel} / ${summary.lowestCategory.daysLabel} Tage</div>
              </div>
            </div>
          </div>

          ${this._collapsed ? "" : html`
            <div class="category-grid">
              ${summary.categories.map((category) => html`
                <div class="category-card">
                  <div class="category-head">
                    <div class="category-title">
                      <ha-icon class="category-icon" icon="${category.icon}"></ha-icon>
                      <div class="category-title-text">${category.title}</div>
                    </div>
                    <div class="score-pill ${category.tone}">${category.scoreLabel}</div>
                  </div>

                  <div class="progress-rail">
                    <div class="progress-fill ${category.tone}" style="width: ${category.progressPercent}%;"></div>
                  </div>

                  <div class="category-foot meta">
                    <span>Ist: ${category.actualLabel}</span>
                    <span>Ziel: ${category.targetLabel}</span>
                  </div>

                  <div class="meta">
                    Reicht für ca. <strong>${category.daysLabel}</strong> Tage.
                    ${category.matchedCount > 0
                      ? html`Erfasst wurden ${category.matchedCount} passende Produkte.`
                      : html`Aktuell wurde kein passendes Produkt aus Grocy erkannt.`}
                  </div>

                  ${category.scorePercent === 0 ? html`
                    <div class="meta alert">${category.title}: 0% - aktuell nicht abgedeckt.</div>
                  ` : ""}

                  ${category.usesEstimatedAmounts ? html`
                    <div class="meta">
                      Artikel in Stück oder ohne Gewichtseinheit werden mit typischen Packungsgrößen geschätzt.
                    </div>
                  ` : ""}

                  <div class="chip-row">
                    ${category.alternatives.map((item) => html`<span class="chip">${item}</span>`)}
                  </div>

                  ${category.matchedItems.length > 0 ? html`
                    <div class="matched-list">${category.matchedItems.join(", ")}</div>
                  ` : ""}
                </div>
              `)}
            </div>

            <div class="footer-note">
              ${summary.expiredCount > 0 ? html`
                <div class="meta alert">
                  ${summary.expiredCount} abgelaufene Artikel werden nicht mitgezählt – bitte in Grocy prüfen.
                </div>
              ` : ""}
              Quelle der Richtwerte: Bundeszentrum für Ernährung / BLE.
              Der offizielle Kalkulator auf ${this._renderLink(EMERGENCY_SOURCE_URL)} nutzt Personen gesamt und Tage,
              die getrennte Erwachsenen-/Kinderlogik wird hier lokal aus den BLE-Mengen abgeleitet.
              <div class="card-version">Karten-/Integrationsversion: ${integrationVersion}</div>
            </div>
          `}
        </div>
      </ha-card>
    `;
  }

  _toggleCollapsed = () => {
    if (this.config?.collapsible === false) return;
    this._collapsed = !this._collapsed;
  };

  _renderLink(url) {
    return html`<a href="${url}" target="_blank" rel="noreferrer">ernaehrungsvorsorge.de</a>`;
  }

  _toNonNegativeNumber(value) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  _toPositiveInt(value, fallback, allowZero = false) {
    const parsed = Number.parseInt(value, 10);
    if (Number.isNaN(parsed)) return fallback;
    if (allowZero) return Math.max(0, parsed);
    return Math.max(1, parsed);
  }

  _buildSummary(stockItems, adults, children, days, waterLiters = 0, kcalPerAdult = DEFAULT_KCAL_PER_ADULT) {
    const usableStockItems = stockItems.filter((item) => item?.status !== "expired");
    const groupMap = this._getProductGroupMap();
    const itemsByCategory = new Map(EMERGENCY_CATEGORY_IDS.map((id) => [id, []]));
    usableStockItems.forEach((item) => {
      const categoryId = this._categorizeItem(item, groupMap);
      if (categoryId) itemsByCategory.get(categoryId).push(item);
    });

    const categories = EMERGENCY_CATEGORIES.map((category) => {
      const targetAmount = this._getCategoryTarget(category, adults, children, days);
      const dailyAmount = this._getCategoryTarget(category, adults, children, 1);
      const matchedItems = itemsByCategory.get(category.id)
        .map((item) => ({ item, convertedAmount: this._convertStockAmount(item, category) }))
        .filter((entry) => entry.convertedAmount > 0)
        .sort((a, b) => b.convertedAmount - a.convertedAmount);
      const externalAmount = category.id === "drinks" ? waterLiters : 0;
      const actualAmount = matchedItems.reduce((sum, entry) => sum + entry.convertedAmount, 0) + externalAmount;
      const rawScore = targetAmount > 0 ? (actualAmount / targetAmount) * 100 : 0;
      const scorePercent = Math.max(0, Math.min(100, rawScore));
      const daysCoverage = dailyAmount > 0 ? actualAmount / dailyAmount : 0;
      const tone = scorePercent >= 100 ? "" : scorePercent >= 50 ? "low" : "critical";
      const progressPercent = scorePercent <= 0 ? 0 : Math.max(4, Math.min(100, Math.round(scorePercent)));
      const matchedNames = matchedItems.map((entry) => entry.item.name);
      if (externalAmount > 0) matchedNames.unshift(`Wasser extern (${this._formatMeasuredAmount(externalAmount, "liters")})`);

      return {
        ...category,
        actualAmount,
        targetAmount,
        daysCoverage,
        usesEstimatedAmounts: matchedItems.some((entry) => this._usesEstimatedAmount(entry.item, category)),
        progressPercent,
        scorePercent,
        scoreLabel: `${Math.round(scorePercent)}%`,
        tone,
        daysLabel: this._formatDays(daysCoverage),
        actualLabel: this._formatMeasuredAmount(actualAmount, category.measurement),
        targetLabel: this._formatMeasuredAmount(targetAmount, category.measurement),
        matchedCount: matchedNames.length,
        matchedItems: matchedNames.slice(0, 6),
      };
    });

    const lowestCategory = categories.reduce((lowest, current) => (
      !lowest || current.daysCoverage < lowest.daysCoverage ? current : lowest
    ), null);
    const averageScorePercent = categories.length > 0
      ? categories.reduce((sum, category) => sum + category.scorePercent, 0) / categories.length
      : 0;

    return {
      categories,
      categoriesAtTarget: categories.filter((category) => category.actualAmount >= category.targetAmount).length,
      averageScorePercent,
      lowestDaysCoverage: lowestCategory?.daysCoverage || 0,
      lowestCategory: lowestCategory || categories[0],
      zeroCategories: categories.filter((category) => category.scorePercent === 0),
      expiredCount: stockItems.length - usableStockItems.length,
      kcal: this._buildKcalSummary(usableStockItems, groupMap, adults, children, kcalPerAdult),
    };
  }

  // Kalorien-Reichweite: Summe aus Menge × kcal je Lagereinheit (Grocy-Feld "Kalorien") über alle
  // Artikel, die in einer der Gruppen zählen. Artikel ohne gepflegten Wert zählen mit 0 und werden benannt.
  _buildKcalSummary(usableStockItems, groupMap, adults, children, kcalPerAdult) {
    const dailyNeed = kcalPerAdult * adults + kcalPerAdult * DEFAULT_CHILD_FOOD_FACTOR * children;
    let total = 0;
    let counted = 0;
    const missing = [];
    usableStockItems.forEach((item) => {
      if (!this._categorizeItem(item, groupMap)) return;
      const calories = Number(item?.calories);
      const amount = Number(item?.amount);
      if (Number.isFinite(calories) && calories > 0 && Number.isFinite(amount) && amount > 0) {
        total += calories * amount;
        counted += 1;
      } else {
        missing.push(item?.name || "?");
      }
    });

    const days = dailyNeed > 0 ? total / dailyNeed : 0;
    const totalLabel = `${Math.round(total).toLocaleString("de-DE")} kcal`;
    const need = `Bedarf ${Math.round(dailyNeed).toLocaleString("de-DE")} kcal/Tag`;
    let label;
    let detail;
    if (counted === 0) {
      label = "Keine Daten";
      detail = "In Grocy sind für diese Artikel keine Kalorien gepflegt";
    } else {
      label = this._formatCoverageLabel(days);
      detail = `${totalLabel} · ${need}`;
    }
    const shown = missing.slice(0, 8).join(", ");
    const warning = missing.length > 0 && counted > 0
      ? `${missing.length} Artikel ohne Kalorien in Grocy, nicht mitgezählt: ${shown}${missing.length > 8 ? " …" : ""}`
      : "";
    return { total, days, dailyNeed, counted, missingCount: missing.length, missingNames: missing.slice(0, 8), label, detail, warning };
  }

  _getCategoryTarget(category, adults, children, days) {
    const adultShare = category.adultDailyTarget * adults * days;
    const childPerDay = category.childDailyTarget ?? category.adultDailyTarget * DEFAULT_CHILD_FOOD_FACTOR;
    return adultShare + (childPerDay * children * days);
  }

  // Eigene Zuordnung aus der Kartenkonfiguration: { "Nudeln": "grain", "Gewürze": "none" }.
  _getProductGroupMap() {
    const configured = this.config?.product_groups;
    const map = new Map();
    if (!configured || typeof configured !== "object") return map;
    Object.entries(configured).forEach(([group, target]) => {
      const key = normalizeEmergencyText(group);
      const value = normalizeEmergencyText(target);
      if (!key) return;
      if (EMERGENCY_IGNORE_IDS.includes(value)) map.set(key, null);
      else if (EMERGENCY_CATEGORY_IDS.includes(value)) map.set(key, value);
    });
    return map;
  }

  // Liefert die eine Gruppe, in der ein Artikel zählt, oder null.
  // Reihenfolge: eigene Produktgruppen-Zuordnung, bekannte Grocy-Produktgruppen,
  // feste Regeln, Suchbegriffe in der Reihenfolge der Gruppen.
  _categorizeItem(item, groupMap = this._getProductGroupMap()) {
    const group = normalizeEmergencyText(item?.product_group);
    if (group) {
      if (groupMap.has(group)) return groupMap.get(group);
      const groupRule = EMERGENCY_GROUP_DEFAULTS.find((rule) => rule.pattern.test(group));
      if (groupRule) return groupRule.category;
    }

    const name = normalizeEmergencyText(item?.name);
    if (!name) return null;
    const rule = EMERGENCY_RULES.find((entry) => entry.pattern.test(name));
    if (rule) return rule.category;

    const tokens = name.split(" ");
    const category = EMERGENCY_CATEGORIES.find((entry) => (
      entry.keywords.some((keyword) => matchesEmergencyKeyword(tokens, keyword))
    ));
    return category ? category.id : null;
  }

  _normalizeText(value) {
    return normalizeEmergencyText(value);
  }

  _normalizeUnit(value) {
    const raw = this._normalizeText(value);
    const mapping = {
      g: "g",
      gram: "g",
      gramm: "g",
      gr: "g",
      kg: "kg",
      mg: "mg",
      ml: "ml",
      l: "l",
      liter: "l",
      cl: "cl",
      dl: "dl",
      st: "piece",
      stk: "piece",
      stck: "piece",
      stueck: "piece",
      stuck: "piece",
      piece: "piece",
      pcs: "piece",
      portion: "piece",
    };
    return mapping[raw] || raw;
  }

  _convertStockAmount(item, category) {
    const amount = Number(item.amount) || 0;
    const unit = this._normalizeUnit(item.unit);
    if (amount <= 0) return 0;

    if (category.measurement === "liters") {
      if (unit === "l") return amount;
      if (unit === "ml") return amount / 1000;
      if (unit === "cl") return amount / 100;
      if (unit === "dl") return amount / 10;
      return this._estimateUnitlessAmount(item, category);
    }

    const density = category.id === "fats" ? OIL_DENSITY : 1;
    if (unit === "kg") return amount * 1000;
    if (unit === "g") return amount;
    if (unit === "mg") return amount / 1000;
    if (unit === "ml") return amount * density;
    if (unit === "cl") return amount * 10 * density;
    if (unit === "dl") return amount * 100 * density;
    if (unit === "l") return amount * 1000 * density;
    // Stück, Packungen und unbekannte Einheiten: typische Packungsgröße schätzen.
    return this._estimateUnitlessAmount(item, category);
  }

  _estimateUnitlessAmount(item, category) {
    const amount = Number(item.amount) || 0;
    if (amount <= 0) return 0;

    const normalizedName = normalizeEmergencyText(item.name);
    const estimates = EMERGENCY_UNITLESS_ESTIMATES[category.id] || [];
    const estimate = estimates.find((entry) => entry.pattern.test(normalizedName));

    if (category.measurement === "liters") return estimate?.liters ? amount * estimate.liters : 0;
    if (estimate?.grams) return amount * estimate.grams;
    return amount * (EMERGENCY_FALLBACK_GRAMS[category.id] || 0);
  }

  _usesEstimatedAmount(item, category) {
    const unit = this._normalizeUnit(item.unit);
    const measured = category.measurement === "liters"
      ? ["l", "ml", "cl", "dl"]
      : ["kg", "g", "mg", "l", "ml", "cl", "dl"];
    return !measured.includes(unit) && this._estimateUnitlessAmount(item, category) > 0;
  }

  _formatMeasuredAmount(amount, measurement) {
    if (measurement === "liters") {
      return `${amount.toFixed(amount >= 10 ? 0 : 1)} l`;
    }

    if (amount >= 1000) {
      return `${(amount / 1000).toFixed(amount >= 10000 ? 0 : 1)} kg`;
    }
    return `${Math.round(amount)} g`;
  }

  _formatDays(value) {
    if (!Number.isFinite(value) || value <= 0) return "0";
    if (value >= 10) return `${Math.floor(value)}`;
    return value.toFixed(1);
  }

  _formatCoverageLabel(value) {
    if (!Number.isFinite(value) || value <= 0) return "Nicht abgedeckt";
    if (value < 1) return "< 1 Tag";
    if (value >= 10) return `${Math.floor(value)} Tage`;
    return `${value.toFixed(1)} Tage`;
  }

  _formatPercent(value) {
    if (!Number.isFinite(value) || value <= 0) return "0%";
    return `${Math.round(value)}%`;
  }

  // Der Vorrat reicht nur so lange wie die schwächste Gruppe.
  _formatOverallCoverage(summary, targetDays) {
    const label = this._formatCoverageLabel(summary.lowestDaysCoverage);
    const average = this._formatPercent(summary.averageScorePercent);
    if (!Number.isFinite(summary.lowestDaysCoverage) || summary.lowestDaysCoverage <= 0) {
      return {
        label,
        detail: `${summary.lowestCategory.title} fehlt · Ø Abdeckung ${average}`,
      };
    }

    const goal = summary.lowestDaysCoverage >= targetDays ? "Ziel erreicht" : `Ziel ${targetDays} Tage`;
    return {
      label,
      detail: `begrenzt durch ${summary.lowestCategory.title} · ${goal} · Ø Abdeckung ${average}`,
    };
  }
}

if (!customElements.get("mealie-grocy-emergency-card")) {
  customElements.define("mealie-grocy-emergency-card", MealieGrocyEmergencyCard);
}

class MealieGrocyInventoryCardEditor extends LitElement {
  static get properties() {
    return { hass: {}, _config: {} };
  }

  setConfig(config) {
    this._config = config;
  }

  render() {
    if (!this.hass || !this._config) return html``;
    const schema = [
      { name: "entity", label: "Bestands-Sensor", selector: { entity: { domain: "sensor" } } },
      { name: "show_empty_location", label: "Nicht zugeordnete Artikel anzeigen", selector: { boolean: {} } },
    ];
    return html`
      <ha-form
        .hass=${this.hass}
        .data=${this._config}
        .schema=${schema}
        .computeLabel=${(item) => item.label}
        @value-changed=${this._valueChanged}
      ></ha-form>
    `;
  }

  _valueChanged(event) {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: event.detail.value },
      bubbles: true,
      composed: true,
    }));
  }
}

if (!customElements.get("mealie-grocy-inventory-card-editor")) {
  customElements.define("mealie-grocy-inventory-card-editor", MealieGrocyInventoryCardEditor);
}

class MealieGrocyInventoryCard extends LitElement {
  static get properties() {
    return { hass: {}, config: {}, _searchTerm: { type: String } };
  }

  constructor() {
    super();
    this._searchTerm = "";
  }

  static getConfigElement() {
    return document.createElement("mealie-grocy-inventory-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_bestand",
      show_empty_location: true,
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Eine Kartenkonfiguration ist erforderlich.");
    this.config = config;
  }

  static get styles() {
    return css`
      :host { display: block; width: 100%; }
      ha-card { padding: 20px; }
      .header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
      .eyebrow { display: flex; align-items: center; gap: 8px; color: var(--secondary-text-color); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
      h2 { margin: 5px 0 0; font-size: 1.35rem; }
      .total { min-width: 54px; text-align: center; padding: 8px 12px; border-radius: 14px; background: var(--secondary-background-color); }
      .total strong { display: block; font-size: 1.2rem; }
      .total span { color: var(--secondary-text-color); font-size: 0.72rem; }
      .search { display: flex; align-items: center; gap: 9px; margin-bottom: 18px; padding: 0 12px; border: 1px solid var(--divider-color); border-radius: 12px; background: var(--secondary-background-color); }
      .search:focus-within { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color); }
      .search ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 20px; }
      .search input { flex: 1; min-width: 0; height: 42px; border: 0; outline: 0; background: transparent; color: var(--primary-text-color); font: inherit; }
      .search input::placeholder { color: var(--secondary-text-color); opacity: 1; }
      .search-clear { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 0; border-radius: 50%; background: transparent; color: var(--secondary-text-color); cursor: pointer; }
      .search-clear:hover, .search-clear:focus-visible { background: var(--divider-color); color: var(--primary-text-color); outline: none; }
      .search-clear ha-icon { --mdc-icon-size: 18px; }
      .locations { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
      .location { border: 1px solid var(--divider-color); border-radius: 14px; overflow: hidden; background: var(--card-background-color); }
      .location-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 14px; background: var(--secondary-background-color); }
      .location-name { display: flex; align-items: center; gap: 8px; font-weight: 650; }
      .count { color: var(--secondary-text-color); font-size: 0.78rem; }
      .items { display: grid; }
      .item { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--divider-color); }
      .item:first-child { border-top: 0; }
      .name { min-width: 0; overflow-wrap: anywhere; }
      .meta { margin-top: 2px; color: var(--secondary-text-color); font-size: 0.74rem; }
      .amount { white-space: nowrap; font-variant-numeric: tabular-nums; }
      .status { display: inline-block; margin-left: 6px; padding: 2px 6px; border-radius: 999px; font-size: 0.68rem; }
      .status.expiring { color: var(--warning-color); background: color-mix(in srgb, var(--warning-color) 14%, transparent); }
      .status.expired { color: var(--error-color); background: color-mix(in srgb, var(--error-color) 14%, transparent); }
      .empty { color: var(--secondary-text-color); text-align: center; padding: 28px 12px; }
      @media (max-width: 600px) { ha-card { padding: 14px; } .locations { grid-template-columns: 1fr; } }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;
    const entityId = this.config.entity || "sensor.mealie_grocy_bestand";
    const stateObj = this.hass.states[entityId];
    if (!stateObj) return html`<ha-card>Bestands-Sensor ${entityId} nicht gefunden.</ha-card>`;

    const items = Array.isArray(stateObj.attributes?.items) ? stateObj.attributes.items : [];
    const eligibleItems = items.filter(
      (item) => this.config.show_empty_location !== false || item?.location !== "Nicht zugeordnet"
    );
    const filteredItems = this._filterItems(eligibleItems);
    const grouped = this._groupByLocation(filteredItems);
    const hasSearch = Boolean(this._searchTerm.trim());

    return html`
      <ha-card>
        <div class="header">
          <div>
            <div class="eyebrow"><ha-icon icon="mdi:warehouse"></ha-icon> Grocy-Bestand</div>
            <h2>Bestand nach Lagerort</h2>
          </div>
          <div class="total">
            <strong>${filteredItems.length}</strong>
            <span>${hasSearch ? `von ${eligibleItems.length}` : "Positionen"}</span>
          </div>
        </div>
        <div class="search">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input
            type="search"
            placeholder="Artikel, Lagerort, Gruppe oder Status suchen …"
            aria-label="Bestand durchsuchen"
            .value=${this._searchTerm}
            @input=${this._handleSearchInput}
          >
          ${hasSearch ? html`
            <button class="search-clear" type="button" title="Suche zurücksetzen" aria-label="Suche zurücksetzen" @click=${this._clearSearch}>
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          ` : ""}
        </div>
        ${grouped.length ? html`
          <div class="locations">
            ${grouped.map((group) => html`
              <section class="location">
                <div class="location-head">
                  <div class="location-name"><ha-icon icon="mdi:map-marker-outline"></ha-icon>${group.name}</div>
                  <div class="count">${group.items.length} Artikel</div>
                </div>
                <div class="items">
                  ${group.items.map((item) => html`
                    <div class="item">
                      <div class="name">
                        ${item.name || "Unbekannter Artikel"}
                        ${item.status === "expiring" || item.status === "expired" ? html`
                          <span class="status ${item.status}">${item.status === "expired" ? "abgelaufen" : "läuft bald ab"}</span>
                        ` : ""}
                        ${item.best_before_date && !String(item.best_before_date).startsWith("2999") ? html`
                          <div class="meta">MHD ${this._formatDate(item.best_before_date)}</div>
                        ` : ""}
                      </div>
                      <div class="amount">${this._formatAmount(item.amount)} ${item.unit || ""}</div>
                    </div>
                  `)}
                </div>
              </section>
            `)}
          </div>
        ` : html`
          <div class="empty">
            ${hasSearch ? `Keine passenden Artikel für „${this._searchTerm.trim()}“ gefunden.` : "Aktuell ist kein Bestand verfügbar."}
          </div>
        `}
      </ha-card>
    `;
  }

  _handleSearchInput(event) {
    this._searchTerm = event?.target?.value || "";
  }

  _clearSearch() {
    this._searchTerm = "";
  }

  _filterItems(items) {
    const searchTerm = this._normalizeSearchText(this._searchTerm);
    if (!searchTerm) return items;

    const statusLabels = {
      expired: "abgelaufen",
      expiring: "läuft bald ab laeuft bald ab bald fällig bald faellig",
      normal: "normal haltbar",
    };
    return items.filter((item) => {
      const searchableText = [
        item?.name,
        item?.location,
        item?.product_group,
        item?.unit,
        item?.status,
        statusLabels[item?.status],
        item?.best_before_date,
        item?.best_before_date ? this._formatDate(item.best_before_date) : null,
        item?.amount,
        item?.amount !== undefined && item?.amount !== null ? this._formatAmount(item.amount) : null,
      ].filter((value) => value !== undefined && value !== null).join(" ");
      return this._normalizeSearchText(searchableText).includes(searchTerm);
    });
  }

  _normalizeSearchText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ß/g, "ss")
      .trim();
  }

  _groupByLocation(items) {
    const groups = new Map();
    items.forEach((item) => {
      const location = String(item?.location || "Nicht zugeordnet").trim() || "Nicht zugeordnet";
      if (!groups.has(location)) groups.set(location, []);
      groups.get(location).push(item);
    });
    return [...groups.entries()]
      .map(([name, locationItems]) => ({
        name,
        items: [...locationItems].sort((a, b) => String(a?.name || "").localeCompare(String(b?.name || ""), "de")),
      }))
      .sort((a, b) => a.name.localeCompare(b.name, "de"));
  }

  _formatAmount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "0";
    return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(amount);
  }

  _formatDate(value) {
    const parts = String(value || "").slice(0, 10).split("-");
    if (parts.length !== 3) return value;
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  }
}

if (!customElements.get("mealie-grocy-inventory-card")) {
  customElements.define("mealie-grocy-inventory-card", MealieGrocyInventoryCard);
}

window.customCards = window.customCards || [];
[
  { type: "mealie-grocy-card", name: "Mealie Grocy Rezepte & Essensplanung", description: "Kochvorschläge und Mealie-Speiseplan" },
  { type: "mealie-grocy-inventory-card", name: "Mealie Grocy Bestand", description: "Grocy-Bestand gruppiert nach Lagerorten" },
  { type: "mealie-grocy-emergency-card", name: "Mealie Grocy Vorrat", description: "Bewertung des Notvorrats" },
].forEach((card) => {
  if (!window.customCards.some((existing) => existing.type === card.type)) window.customCards.push(card);
});

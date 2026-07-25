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
customElements.define("mealie-grocy-card-editor", MealieGrocyCardEditor);

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
                        <button type="button" class="btn btn-shopping" title="Zur Einkaufsliste hinzufügen" @click=${() => this._callBridgeService("add_missing_ingredients", recipe._globalIndex)}>
                          <ha-icon icon="mdi:cart-plus"></ha-icon>
                        </button>
                        <button type="button" class="btn btn-calendar" title="Zum Speiseplan hinzufügen" @click=${() => this._callBridgeService("set_to_next_free_day", recipe._globalIndex)}>
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

  _callBridgeService(serviceName, index) {
    const payload = {
      recipe_index: index,
    };

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

customElements.define("mealie-grocy-card", MealieGrocyCard);

const EMERGENCY_SOURCE_URL = "https://www.ernaehrungsvorsorge.de/private-vorsorge/notvorrat/vorratskalkulator";
const DEFAULT_CHILD_FOOD_FACTOR = 0.7;
const DEFAULT_CHILD_DRINK_LITERS_PER_DAY = 1;

const EMERGENCY_CATEGORIES = [
  {
    id: "grain",
    title: "Getreide, Brot, Kartoffeln",
    icon: "mdi:bread-slice-outline",
    measurement: "grams",
    adultDailyTarget: 330,
    alternatives: ["Brot", "Knackebrot", "Reis", "Nudeln", "Haferflocken", "Kartoffeln"],
    keywords: [
      "brot", "knackebrot", "reis", "nudel", "hafer", "muesli", "musli", "griess", "gries",
      "mehl", "wrap", "tortilla", "kartoffel", "couscous", "bulgur", "quinoa", "toast"
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
      "gemuese", "gemuse", "tomat", "passata", "erbs", "mais", "bohn", "linse", "karott",
      "mohrr", "paprika", "gurke", "zucchini", "sauerkraut", "rotkohl", "pilz", "champignon",
      "kichererb", "spinat", "mangold", "brokkoli", "brocoli", "blumenkohl"
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
      "obst", "apfel", "birn", "pfirs", "aprik", "mandarin", "orange", "ananas", "beere",
      "rosin", "trockenobst", "pflaum", "mango", "banan", "kirsch", "nus", "mandel",
      "cashew", "walnuss", "haselnuss", "erdnuss"
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
      "milch", "joghurt", "kaese", "kase", "quark", "skyr", "kefir", "sahne", "kondensmilch",
      "buttermilch", "mozarella", "mozzarella", "feta", "pflanzendrink", "haferdrink", "sojadrink"
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
      "fleisch", "fisch", "ei", "eier", "wurst", "schinken", "thunfisch", "makrele", "sardine",
      "huhn", "chicken", "pute", "rind", "schwein", "tofu", "tempeh", "lupine", "seitan",
      "hack", "salami", "frikadell", "bratwurst"
    ],
  },
  {
    id: "fats",
    title: "Fette und Öle",
    icon: "mdi:bottle-tonic-plus-outline",
    measurement: "grams",
    adultDailyTarget: 35,
    alternatives: ["Öl", "Butter", "Margarine", "Schmalz", "Nussmus"],
    keywords: [
      "oel", "ol", "olivenoel", "rapsoel", "sonnenblumenoel", "butter", "margarine",
      "schmalz", "nussmus", "erdnussbutter", "kokosoel", "ghee"
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
    keywords: [
      "wasser", "saft", "tee", "kaffee", "cola", "limonade", "schorle", "getraenk", "getrank",
      "sirup", "iso", "trink"
    ],
  },
];

const EMERGENCY_UNITLESS_ESTIMATES = {
  grain: [
    { pattern: /\b(mehl)\b/, grams: 1000 },
    { pattern: /\b(reis|linsen|graupen|grie|hafer|muesli|musli)\b/, grams: 500 },
    { pattern: /\b(asia nudeln|ramen|ramyun|yumyum|yum yum|udonnoodle|udon noodle|jjajang|neoguri|shin|chapaghetti|shrimp ramen|wan tan nudeln)\b/, grams: 75 },
    { pattern: /\b(nudel|spaghetti|fusilli|farfalle|penne|rigate|tortiglioni|lasagneplatten|spatzle|spaetzle|gnocchi)\b/, grams: 500 },
    { pattern: /\b(kartoffelpuree|kartoffelbrei)\b/, grams: 250 },
    { pattern: /\b(brot|toast|laugenstangen|chapathi|chapati|durum|dürüm|wrap|taco)\b/, grams: 250 },
  ],
  vegetables: [
    { pattern: /\b(passierte tomaten|tomaten gehackt|tomatensosse|tomatensoße|tomatenmark|paprikamark)\b/, grams: 400 },
    { pattern: /\b(erbse|mohren|möhren|mais|bohn|kichererb|linsen|sauerkraut|rotkraut|spinat|blumenkohl|gemuse|gemuese|brokk|kohlrabi|suppen)\b/, grams: 400 },
  ],
  fruit: [
    { pattern: /\b(apfelmus)\b/, grams: 360 },
    { pattern: /\b(mandarin|orange|pfirs|aprik|ananas|sauerkirsch)\b/, grams: 300 },
    { pattern: /\b(nuss|erdnuss|pekannuss|pistaz)\b/, grams: 200 },
  ],
  milk: [
    { pattern: /\b(milch)\b/, grams: 1000 },
    { pattern: /\b(sahne|schlagsahne)\b/, grams: 200 },
    { pattern: /\b(kondensmilch)\b/, grams: 170 },
    { pattern: /\b(kaese|käse|schmelzkase|schmelzkäse)\b/, grams: 200 },
  ],
  protein: [
    { pattern: /\b(thunfisch|fischfilet|fischstabchen|fischstäbchen|corned beef)\b/, grams: 200 },
    { pattern: /\b(wurst|würstchen|bratwurst|nurnberger|nürnberger|schinken|hack|gulasch|huhn|hahnchen|hähnchen|chicken|pute|rind|garnelen|prawns)\b/, grams: 250 },
    { pattern: /\b(ei|eier)\b/, grams: 53 },
    { pattern: /\b(tofu|tempeh|protein chunks)\b/, grams: 200 },
  ],
  fats: [
    { pattern: /\b(olivenol|olivenöl|sonnenblumenol|sonnenblumenöl|rapsol|rapsöl|erdnusspaste|erdnussbutter)\b/, grams: 500 },
    { pattern: /\b(butter|margarine)\b/, grams: 250 },
  ],
  drinks: [
    { pattern: /\b(wasser)\b/, liters: 1.5 },
    { pattern: /\b(milch)\b/, liters: 1 },
    { pattern: /\b(sahne)\b/, liters: 0.2 },
    { pattern: /\b(kondensmilch)\b/, liters: 0.17 },
    { pattern: /\b(mineralwasser|trinkwasser|saft|cola|limonade|schorle|getrank|getraenk)\b/, liters: 1 },
  ],
};

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
      </div>
    `;
  }

  _valueChanged(ev) {
    const config = { ...ev.detail.value };

    ["adults", "children", "days"].forEach((key) => {
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
customElements.define("mealie-grocy-emergency-card-editor", MealieGrocyEmergencyCardEditor);

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

      @media (max-width: 700px) {
        .hero {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  static getStubConfig() {
    return {
      entity: "sensor.mealie_grocy_kochvorschlage",
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

    const entityId = this.config.entity || "sensor.mealie_grocy_kochvorschlage";
    const stateObj = this.hass.states[entityId];

    if (!stateObj || !stateObj.attributes?.stock_items) {
      return html`<ha-card>Warte auf Grocy-Bestandsdaten...</ha-card>`;
    }

    const adults = this._toPositiveInt(this.config.adults, 2);
    const children = this._toPositiveInt(this.config.children, 0, true);
    const days = this._toPositiveInt(this.config.days, 10);
    const collapsible = this.config.collapsible !== false;
    const stockItems = stateObj.attributes.stock_items || [];
    const summary = this._buildSummary(stockItems, adults, children, days);
    const overallDaysLabel = this._formatCoverageLabel(summary.overallDaysCoverage);

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
                <span class="hero-stat-label">Vollständig abgedeckt</span>
                <div class="hero-stat-value">${overallDaysLabel}</div>
                <div class="hero-stat-sub">begrenzt durch die knappste Kategorie</div>
              </div>
              <div class="hero-stat">
                <span class="hero-stat-label">Gruppen im Ziel</span>
                <div class="hero-stat-value">${summary.categoriesAtTarget}/${summary.categories.length}</div>
                <div class="hero-stat-sub">${summary.lowestCategory.title}: ${summary.lowestCategory.scoreLabel}</div>
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
                    ${category.matchedItems.length > 0
                      ? html`Erfasst wurden ${category.matchedItems.length} passende Produkte.`
                      : html`Aktuell wurde kein passendes Produkt aus Grocy erkannt.`}
                  </div>

                  ${category.usesEstimatedAmounts ? html`
                    <div class="meta">
                      Artikel ohne Grocy-Einheit werden aktuell mit typischen Packungsgrößen geschätzt.
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
              Quelle der Richtwerte: Bundeszentrum für Ernährung / BLE.
              Der offizielle Kalkulator auf ${this._renderLink(EMERGENCY_SOURCE_URL)} nutzt Personen gesamt und Tage,
              die getrennte Erwachsenen-/Kinderlogik wird hier lokal aus den BLE-Mengen abgeleitet.
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

  _toPositiveInt(value, fallback, allowZero = false) {
    const parsed = Number.parseInt(value, 10);
    if (Number.isNaN(parsed)) return fallback;
    if (allowZero) return Math.max(0, parsed);
    return Math.max(1, parsed);
  }

  _buildSummary(stockItems, adults, children, days) {
    const categories = EMERGENCY_CATEGORIES.map((category) => {
      const targetAmount = this._getCategoryTarget(category, adults, children, days);
      const dailyAmount = this._getCategoryTarget(category, adults, children, 1);
      const matchedItems = stockItems.filter((item) => this._matchesCategory(item, category));
      const actualAmount = matchedItems.reduce(
        (sum, item) => sum + this._convertStockAmount(item, category),
        0,
      );
      const rawScore = targetAmount > 0 ? (actualAmount / targetAmount) * 100 : 0;
      const scorePercent = Math.max(0, Math.min(100, rawScore));
      const daysCoverage = dailyAmount > 0 ? actualAmount / dailyAmount : 0;
      const tone = scorePercent >= 100 ? "" : scorePercent >= 50 ? "low" : "critical";
      const progressPercent = scorePercent <= 0 ? 0 : Math.max(4, Math.min(100, Math.round(scorePercent)));

      return {
        ...category,
        actualAmount,
        targetAmount,
        daysCoverage,
        usesEstimatedAmounts: matchedItems.some((item) => this._usesEstimatedAmount(item, category)),
        progressPercent,
        scoreLabel: `${Math.round(scorePercent)}%`,
        tone,
        daysLabel: this._formatDays(daysCoverage),
        actualLabel: this._formatMeasuredAmount(actualAmount, category.measurement),
        targetLabel: this._formatMeasuredAmount(targetAmount, category.measurement),
        matchedItems: matchedItems.slice(0, 6).map((item) => item.name),
      };
    });

    const lowestCategory = categories.reduce((lowest, current) => (
      !lowest || current.daysCoverage < lowest.daysCoverage ? current : lowest
    ), null);

    return {
      categories,
      categoriesAtTarget: categories.filter((category) => category.actualAmount >= category.targetAmount).length,
      overallDaysCoverage: lowestCategory?.daysCoverage || 0,
      lowestCategory: lowestCategory || categories[0],
    };
  }

  _getCategoryTarget(category, adults, children, days) {
    const adultShare = category.adultDailyTarget * adults * days;
    const childPerDay = category.childDailyTarget
      ?? (category.measurement === "liters"
        ? category.adultDailyTarget * DEFAULT_CHILD_FOOD_FACTOR
        : category.adultDailyTarget * DEFAULT_CHILD_FOOD_FACTOR);
    return adultShare + (childPerDay * children * days);
  }

  _matchesCategory(item, category) {
    if (this._isExcludedCategoryMatch(item, category)) {
      return false;
    }

    const haystack = this._normalizeText([
      item.name,
      item.product_group,
      item.location,
    ].filter(Boolean).join(" "));
    const tokens = haystack.split(" ").filter(Boolean);

    return category.keywords.some((keyword) => {
      const normalizedKeyword = this._normalizeText(keyword);
      if (!normalizedKeyword) return false;
      if (normalizedKeyword.includes(" ")) return haystack.includes(normalizedKeyword);
      return tokens.some((token) => token === normalizedKeyword || token.startsWith(normalizedKeyword));
    });
  }

  _isExcludedCategoryMatch(item, category) {
    const name = this._normalizeText(item?.name);

    if (category.id === "drinks") {
      if (name.includes("kaffeebohnen")) return true;
      if (name.includes("thunfisch") || name.includes("fischfilet")) return true;
      if (name.includes("eigenem saft")) return true;
    }

    if (category.id === "grain") {
      if (name.includes("kartoffelsnacks") || name.includes("chips")) return true;
    }

    return false;
  }

  _normalizeText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
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

    if (unit === "kg") return amount * 1000;
    if (unit === "g") return amount;
    if (unit === "mg") return amount / 1000;
    if (unit === "ml") return amount * this._densityFor(item.name);
    if (unit === "cl") return amount * 10 * this._densityFor(item.name);
    if (unit === "dl") return amount * 100 * this._densityFor(item.name);
    if (unit === "l") return amount * 1000 * this._densityFor(item.name);
    if (unit === "piece") {
      const pieceWeight = this._pieceWeightFor(item.name, category.id);
      if (pieceWeight > 0) return amount * pieceWeight;
    }
    return this._estimateUnitlessAmount(item, category);
  }

  _densityFor(name) {
    const normalized = this._normalizeText(name);
    if (normalized.includes("oel") || normalized.includes("ol")) return 0.92;
    return 1;
  }

  _pieceWeightFor(name, categoryId) {
    const normalized = this._normalizeText(name);
    if (categoryId === "protein" && (/\bei\b/.test(normalized) || /\beier\b/.test(normalized))) return 53;
    return 0;
  }

  _estimateUnitlessAmount(item, category) {
    const amount = Number(item.amount) || 0;
    if (amount <= 0) return 0;

    const normalizedName = this._normalizeText(item.name);
    const estimates = EMERGENCY_UNITLESS_ESTIMATES[category.id] || [];

    for (const estimate of estimates) {
      if (!estimate.pattern.test(normalizedName)) continue;
      if (category.measurement === "liters" && estimate.liters) return amount * estimate.liters;
      if (category.measurement === "grams" && estimate.grams) return amount * estimate.grams;
    }

    if (category.measurement === "liters") return 0;

    const fallbackByCategory = {
      grain: 500,
      vegetables: 400,
      fruit: 250,
      milk: 250,
      protein: 250,
      fats: 500,
    };

    return amount * (fallbackByCategory[category.id] || 0);
  }

  _usesEstimatedAmount(item, category) {
    const unit = this._normalizeUnit(item.unit);
    if (!unit) return this._estimateUnitlessAmount(item, category) > 0;
    if (unit === "piece") return this._pieceWeightFor(item.name, category.id) <= 0;
    return false;
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
}

customElements.define("mealie-grocy-emergency-card", MealieGrocyEmergencyCard);

// Lädt die Notvorratskarte ohne Browser und Home Assistant, damit die Rechenlogik testbar ist.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const CARD_PATH = new URL("../custom_components/mealie_grocy_bridge/frontend/mealie-grocy-card.js", import.meta.url);

export function loadEmergencyCard() {
  const source = readFileSync(CARD_PATH, "utf8").replace(/^import .*$/m, "");
  const context = {
    LitElement: class {},
    html: () => "",
    css: () => "",
    customElements: { get: () => undefined, define: () => {} },
    document: { createElement: () => ({}) },
    window: {},
  };
  vm.createContext(context);
  vm.runInContext(`${source}\nglobalThis.__EmergencyCard = MealieGrocyEmergencyCard;`, context);
  return context.__EmergencyCard;
}

export function createCard(config = {}) {
  const Card = loadEmergencyCard();
  const card = new Card();
  card.config = config;
  return card;
}

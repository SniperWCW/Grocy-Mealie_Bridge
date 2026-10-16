// Unit-Tests für die Notvorratskarte: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createCard } from "./emergency_card_harness.mjs";

const item = (name, amount, unit, extra = {}) => ({
  name, amount, unit, status: "normal", product_group: "", location: "", ...extra,
});

const categoryOf = (card, stockItem) => card._categorizeItem(stockItem);

const amountIn = (card, stockItems, categoryId, options = {}) => {
  const { adults = 2, children = 0, days = 10, water = 0 } = options;
  const summary = card._buildSummary(stockItems, adults, children, days, water);
  return summary.categories.find((category) => category.id === categoryId).actualAmount;
};

test("Stück-Artikel werden über Packungsgrößen geschätzt statt mit 0 g", () => {
  const card = createCard();
  assert.equal(amountIn(card, [item("Thunfischfilets in eigenem Saft", 1, "stück")], "protein"), 180);
  assert.equal(amountIn(card, [item("Passierte Tomaten", 5, "Stück")], "vegetables"), 2000);
  assert.equal(amountIn(card, [item("Risotto Reis", 1, "stück")], "grain"), 500);
  assert.equal(amountIn(card, [item("Eier", 10, "stück")], "protein"), 530);
});

test("Zusammengesetzte Wörter werden erkannt", () => {
  const card = createCard();
  assert.equal(categoryOf(card, item("Glasnudeln", 200, "g")), "grain");
  assert.equal(categoryOf(card, item("Bio-Wienerle", 250, "g")), "protein");
  assert.equal(categoryOf(card, item("Dosenmais", 420, "g")), "vegetables");
  assert.equal(categoryOf(card, item("Geschabte Spätzle", 1000, "g")), "grain");
  assert.equal(categoryOf(card, item("Tomatensoße", 3, "stück")), "vegetables");
});

test("Würzmittel, Snacks und Haushaltsartikel zählen nicht", () => {
  const card = createCard();
  [
    "Pesto Ricotta Walnuss", "Apero Croki l'Epautre Olives et Oignons", "Oliven",
    "Kaffeebohnen Lavazza", "Kokosmilch", "Rinderfond", "Gemüsebrühe", "Crispy Chilli in Oil",
    "Hot Chilli Senf", "Schoko Chunks Vollmilch", "Geschirrreiniger", "Jodsalz", "Zucker",
  ].forEach((name) => assert.equal(categoryOf(card, item(name, 1, "stück")), null, name));
});

test("Speiseöl bleibt Fett, Instant-Nudeln zählen als Getreide", () => {
  const card = createCard();
  assert.equal(categoryOf(card, item("Olivenöl mit Edelkräuter", 1, "stück")), "fats");
  assert.equal(Math.round(amountIn(card, [item("Sonnenblumenöl", 1000, "ml")], "fats")), 920);
  assert.equal(amountIn(card, [item("Shin Ramyun Kimchi", 2, "stück")], "grain"), 150);
});

test("Jeder Artikel zählt in genau einer Gruppe", () => {
  const card = createCard();
  const stock = [item("Buttermilch", 1, "l"), item("Orangensaft", 1, "l"), item("Nussmus", 250, "g")];
  const summary = card._buildSummary(stock, 1, 0, 1, 0);
  const counted = summary.categories.reduce((sum, category) => sum + category.matchedCount, 0);
  assert.equal(counted, 3);
  assert.equal(categoryOf(card, stock[0]), "milk");
  assert.equal(categoryOf(card, stock[1]), "drinks");
  assert.equal(categoryOf(card, stock[2]), "fats");
});

test("Produktgruppen haben Vorrang vor Suchbegriffen", () => {
  const card = createCard({ product_groups: { "Vorrat Süß": "fruit", Nudeln: "none" } });
  assert.equal(categoryOf(card, item("Zucker", 1, "kg", { product_group: "Vorrat Süß" })), "fruit");
  assert.equal(categoryOf(card, item("Fusilli", 500, "g", { product_group: "Nudeln" })), null);
  const defaults = createCard();
  assert.equal(categoryOf(defaults, item("Essigreiniger", 1, "stück", { product_group: "Reinigungsmittel" })), null);
  assert.equal(categoryOf(defaults, item("Collezione", 1, "stück", { product_group: "Nudeln" })), "grain");
});

test("Gesamtreichweite richtet sich nach der schwächsten Gruppe", () => {
  const card = createCard();
  const stock = [item("Sonnenblumenöl", 5, "l"), item("Penne", 3300, "g")];
  const summary = card._buildSummary(stock, 1, 0, 10, 0);
  assert.equal(summary.lowestDaysCoverage, 0);
  assert.equal(card._formatOverallCoverage(summary, 10).label, "Nicht abgedeckt");
});

test("Extern gelagertes Wasser zählt bei Getränken mit", () => {
  const card = createCard();
  assert.equal(amountIn(card, [], "drinks", { water: 20 }), 20);
});

test("Abgelaufene Artikel zählen nicht, werden aber gezählt", () => {
  const card = createCard();
  const summary = card._buildSummary([item("Reis", 1000, "g", { status: "expired" })], 1, 0, 1, 0);
  assert.equal(summary.expiredCount, 1);
  assert.equal(summary.categories.find((category) => category.id === "grain").actualAmount, 0);
});

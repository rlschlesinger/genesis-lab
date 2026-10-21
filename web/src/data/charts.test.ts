import { describe, expect, it } from "vitest";

import type { HistoryColumns } from "../api/types";
import history from "../api/__fixtures__/history.json";
import dietHistory from "../api/__fixtures__/history_diets.json";
import predatorHistory from "../api/__fixtures__/history_predators.json";
import { CHARTS, DIET_CHARTS, PREDATOR_CHARTS, chartsFor, worldsOf } from "./charts";

const ids = (columns: HistoryColumns) => chartsFor(columns).map((c) => c.id);

describe("which charts a history gets", () => {
  it("gives a plain world the four charts, in order", () => {
    expect(worldsOf(history.columns)).toEqual({ hunted: false, twoFoods: false });
    expect(ids(history.columns)).toEqual(CHARTS.map((c) => c.id));
  });

  it("puts a predator world's charts after the population chart", () => {
    expect(worldsOf(predatorHistory.columns)).toEqual({ hunted: true, twoFoods: false });
    expect(ids(predatorHistory.columns)).toEqual([
      "population",
      ...PREDATOR_CHARTS.map((c) => c.id),
      ...CHARTS.slice(1).map((c) => c.id),
    ]);
  });

  it("puts a two-food world's charts there too", () => {
    expect(worldsOf(dietHistory.columns)).toEqual({ hunted: false, twoFoods: true });
    expect(ids(dietHistory.columns)).toEqual([
      "population",
      ...DIET_CHARTS.map((c) => c.id),
      ...CHARTS.slice(1).map((c) => c.id),
    ]);
  });

  it("keeps the diet charts for a two-food world whose organisms have all died", () => {
    // diet_sd is null with nobody alive; the food counts are not, and still worth charting.
    const extinct: HistoryColumns = {
      ...dietHistory.columns,
      population: dietHistory.columns.population.map(() => 0),
      diet_sd: dietHistory.columns.diet_sd.map(() => null),
      diet_low: dietHistory.columns.diet_low.map(() => null),
      diet_high: dietHistory.columns.diet_high.map(() => null),
    };
    expect(worldsOf(extinct).twoFoods).toBe(true);
  });

  it("still counts a world as hunted once its predators are extinct (0, not null)", () => {
    const extinct: HistoryColumns = {
      ...predatorHistory.columns,
      predators: predatorHistory.columns.predators.map(() => 0),
    };
    expect(worldsOf(extinct).hunted).toBe(true);
  });
});

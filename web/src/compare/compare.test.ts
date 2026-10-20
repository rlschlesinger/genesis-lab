import { describe, expect, it } from "vitest";

import type { HistoryColumns } from "../api/types";
import { emptyColumns } from "../analytics/series";
import { alignSeries } from "./align";
import { configDiff } from "./diff";

describe("comparing configs", () => {
  it("lists only what differs, by dotted path", () => {
    const a = { run: { seed: 1, max_ticks: 100 }, food: { regrowth_per_tick: 2 }, organisms: { controller: "neural" } };
    const b = { run: { seed: 2, max_ticks: 100 }, food: { regrowth_per_tick: 1 }, organisms: { controller: "neural" } };
    expect(configDiff(a, b)).toEqual([
      { path: "food.regrowth_per_tick", a: "2", b: "1" },
      { path: "run.seed", a: "1", b: "2" },
    ]);
  });

  it("summarises long lists such as brain weights, and notes absent sections", () => {
    const weights = (v: number) => Array.from({ length: 30 }, () => Array(62).fill(v));
    const diff = configDiff({ brain: { founder_weights: weights(0) } }, { brain: { founder_weights: weights(1) } });
    expect(diff).toEqual([{ path: "brain.founder_weights", a: "30 values (differs)", b: "30 values (differs)" }]);
    expect(configDiff({ brain: { size: 1 } }, {})).toEqual([{ path: "brain.size", a: "1", b: "absent" }]);
    expect(configDiff({ w: [1] }, { w: null })).toEqual([{ path: "w", a: "[1]", b: "none" }]);
  });

  it("finds nothing between identical configs", () => {
    expect(configDiff({ a: { b: [1, 2] } }, { a: { b: [1, 2] } })).toEqual([]);
  });
});

describe("two runs on one axis", () => {
  const cols = (ticks: number[], values: (number | null)[]): HistoryColumns => ({
    ...emptyColumns(),
    tick: ticks,
    population: values as number[],
  });

  it("places each run's points at its own ticks, with gaps elsewhere", () => {
    const [ticks, a, b] = alignSeries(cols([1, 3, 5], [10, 30, 50]), cols([3, 4], [33, 44]), "population");
    expect(ticks).toEqual([1, 3, 4, 5]);
    expect(a).toEqual([10, 30, null, 50]);
    expect(b).toEqual([null, 33, 44, null]);
  });
});

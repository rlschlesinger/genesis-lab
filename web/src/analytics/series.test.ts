import { describe, expect, it } from "vitest";

import history from "../api/__fixtures__/history.json";
import type { History } from "../api/types";
import { MAX_POINTS, apply, chooseEvery, emptyColumns, merge, nextRequest } from "./series";

const page = (ticks: number[], every = 1): History => {
  const columns = emptyColumns();
  for (const key of Object.keys(columns) as (keyof typeof columns)[]) {
    (columns[key] as number[]) = ticks.map((t) => (key === "tick" ? t : t * 10));
  }
  return { run_id: "r", every, columns };
};

describe("chart history", () => {
  it("picks round point sizes that keep charts under the limit", () => {
    expect(chooseEvery(0)).toBe(1);
    expect(chooseEvery(MAX_POINTS)).toBe(1);
    expect(chooseEvery(MAX_POINTS + 1)).toBe(2);
    expect(chooseEvery(20_000)).toBe(50);
    expect(chooseEvery(100_000)).toBe(200);
  });

  it("adds only newer points, keeping every column aligned", () => {
    const a = page([0, 1, 2]).columns;
    const merged = merge(a, page([2, 3, 4]).columns);
    expect(merged.tick).toEqual([0, 1, 2, 3, 4]);
    expect(merged.population).toEqual([0, 10, 20, 30, 40]);
    expect(merge(merged, page([1, 2]).columns)).toBe(merged); // nothing new: unchanged
  });

  it("asks only for what's new, and starts over when points must get coarser", () => {
    expect(nextRequest(null, 100)).toEqual({ since: 0, every: 1, replace: true });
    const series = apply(null, { replace: true }, page([0, 1, 2]));
    expect(nextRequest(series, 3)).toEqual({ since: 3, every: 1, replace: false });
    expect(nextRequest(series, MAX_POINTS * 3)).toEqual({ since: 0, every: 5, replace: true });
  });

  it("reads a real server response", () => {
    const series = apply(null, { replace: true }, history as History);
    expect(series.every).toBe(10);
    expect(series.columns.tick.every((t) => (t + 1) % 10 === 0)).toBe(true);
  });
});

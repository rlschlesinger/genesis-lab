// Keeping a live run's history for charts: how coarse the points are, and adding new ones.

import type { History, HistoryColumns } from "../api/types";

/** At most this many points per chart: about one every 1.5 pixels at a typical chart width,
 *  the most that stays readable (1,500 made the births chart a solid thicket). */
export const MAX_POINTS = 600;
/** Point sizes, in ticks: round numbers, so "each point covers 50 ticks" reads easily. */
const STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000];

/** The smallest round point size that keeps a run of ``ticks`` under MAX_POINTS points. */
export function chooseEvery(ticks: number): number {
  return STEPS.find((every) => ticks / every <= MAX_POINTS) ?? STEPS[STEPS.length - 1]!;
}

export function emptyColumns(): HistoryColumns {
  return {
    tick: [], population: [], food_count: [], lineages: [], mean_energy: [], predators: [],
    food_a: [], food_b: [], diet_sd: [], diet_low: [], diet_high: [],
    births: [], deaths: [], food_eaten: [], attempts: [], captures: [], toward_food: [],
    mean_turn: [], mean_throttle: [],
  };
}

/** Append the points of ``incoming`` that come after what we have (the server never changes
 *  a point once sent, so nothing older is touched). */
export function merge(current: HistoryColumns, incoming: HistoryColumns): HistoryColumns {
  const last = current.tick.length ? current.tick[current.tick.length - 1]! : -1;
  const start = incoming.tick.findIndex((t) => t > last);
  if (start === -1) return current;
  const out = emptyColumns();
  for (const key of Object.keys(out) as (keyof HistoryColumns)[]) {
    (out[key] as (number | null)[]) = [...current[key], ...incoming[key].slice(start)];
  }
  return out;
}

export interface Series {
  every: number;
  columns: HistoryColumns;
}

/** The next fetch: everything again at a coarser size if the run has outgrown this one,
 *  otherwise only what's new. */
export function nextRequest(series: Series | null, tick: number): { since: number; every: number; replace: boolean } {
  const every = Math.max(chooseEvery(tick), series?.every ?? 1);
  if (series === null || every !== series.every) return { since: 0, every, replace: true };
  const ticks = series.columns.tick;
  return { since: ticks.length ? ticks[ticks.length - 1]! + 1 : 0, every, replace: false };
}

export function apply(series: Series | null, request: { replace: boolean }, response: History): Series {
  if (request.replace || series === null || series.every !== response.every) {
    return { every: response.every, columns: response.columns };
  }
  return { every: series.every, columns: merge(series.columns, response.columns) };
}

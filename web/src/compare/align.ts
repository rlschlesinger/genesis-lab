// Two runs on one tick axis, for one chart. uPlot draws series against a shared x array, so
// each run's values are placed at their own ticks and left empty (a gap) elsewhere.

import type { HistoryColumns } from "../api/types";

export function alignSeries(
  a: HistoryColumns,
  b: HistoryColumns,
  column: keyof HistoryColumns,
): [number[], (number | null)[], (number | null)[]] {
  const ticks = [...new Set([...a.tick, ...b.tick])].sort((x, y) => x - y);
  const place = (cols: HistoryColumns) => {
    const at = new Map<number, number | null>();
    cols.tick.forEach((t, i) => at.set(t, cols[column][i] ?? null));
    return ticks.map((t) => (at.has(t) ? at.get(t)! : null));
  };
  return [ticks, place(a), place(b)];
}

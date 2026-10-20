// The Compare view's charts. Two runs may use different point sizes (a 20,000-tick run's
// points cover more ticks than a 1,000-tick run's), so flows are shown as rates per tick;
// stocks and shares compare directly.

import type { HistoryColumns } from "../api/types";

export interface CompareChart {
  id: string;
  title: string;
  describe: string;
  column: keyof HistoryColumns;
  perTick?: boolean;
  range?: [number, number];
}

export const COMPARE_CHARTS: CompareChart[] = [
  { id: "population", title: "Population", column: "population",
    describe: "Organisms alive, counted at the end of each point." },
  { id: "meals", title: "Meals per tick", column: "food_eaten", perTick: true,
    describe: "Meals eaten per tick, averaged over each point (points may cover different numbers of ticks in the two runs)." },
  { id: "energy", title: "Mean energy", column: "mean_energy",
    describe: "Average energy of the organisms alive, in energy units (EU)." },
  { id: "toward", title: "Turning toward seen food", column: "toward_food", range: [0, 1],
    describe: "Share of food-seeing organisms whose turn brought food closer to straight ahead: random turning about 0.5, the seeker 1.0." },
];

export const RUN_COLOURS = { a: "--violet", b: "--iodine" } as const;

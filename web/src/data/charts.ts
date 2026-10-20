// The Analytics view's charts: what each shows, in which unit, and how. Every value comes
// from the server's history (docs/API.md, "History"); nothing here invents a number.

import type { HistoryColumns } from "../api/types";
import type { TokenName } from "../styles/tokens";

export interface ChartSeries {
  column: keyof HistoryColumns;
  label: string;
  colour: TokenName;
  dashed?: boolean;
}

export interface ChartSpec {
  id: string;
  title: string;
  /** What a reader needs to read it right: the unit, and how a point is formed. */
  describe: (every: number) => string;
  series: ChartSeries[];
  range?: [number, number];
}

const per = (every: number) => (every === 1 ? "per tick" : `per ${every.toLocaleString("en")} ticks`);

export const CHARTS: ChartSpec[] = [
  {
    id: "population",
    title: "Population and food",
    describe: (every) =>
      `Organisms alive and food items on the plate, counted at the end of each ${every === 1 ? "tick" : `${every.toLocaleString("en")}-tick interval`}.`,
    series: [
      { column: "population", label: "organisms", colour: "--violet" },
      { column: "food_count", label: "food items", colour: "--iodine" },
    ],
  },
  {
    id: "flows",
    title: "Births, deaths and meals",
    describe: (every) => `Counts ${per(every)}: every birth, death and meal in each interval is included.`,
    series: [
      { column: "births", label: "births", colour: "--violet" },
      { column: "deaths", label: "deaths", colour: "--safranin" },
      { column: "food_eaten", label: "meals", colour: "--iodine", dashed: true },
    ],
  },
  {
    id: "energy",
    title: "Mean energy",
    describe: () => "Average energy of the organisms alive, in energy units (EU). Empty when none are alive.",
    series: [{ column: "mean_energy", label: "mean energy (EU)", colour: "--violet" }],
  },
  {
    id: "behaviour",
    title: "Behaviour",
    describe: (every) =>
      `Shares from 0 to 1, averaged ${per(every)}. Turning toward food is the share of organisms seeing food whose turn brought it closer to straight ahead: random turning scores about 0.5, the hand-written seeker 1.0.`,
    series: [
      { column: "toward_food", label: "turning toward food", colour: "--violet" },
      { column: "mean_throttle", label: "throttle", colour: "--iodine" },
    ],
    range: [0, 1],
  },
];

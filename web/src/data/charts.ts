// The Analytics view's charts: what each shows, in which unit, and how. Every value comes
// from the server's history (docs/API.md, "History"); nothing here invents a number.

import type { HistoryColumns } from "../api/types";
import type { TokenName } from "../styles/tokens";
import { SPECIALIST } from "./diet";

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

/** Charts only a world with predators has (6.5), shown after the population chart. */
export const PREDATOR_CHARTS: ChartSpec[] = [
  {
    id: "predators",
    title: "Prey and predators",
    describe: (every) =>
      `Both species alive, counted at the end of each ${every === 1 ? "tick" : `${every.toLocaleString("en")}-tick interval`}.`,
    series: [
      { column: "population", label: "prey", colour: "--prey" },
      { column: "predators", label: "predators", colour: "--predator" },
    ],
  },
  {
    id: "strikes",
    title: "Strikes and captures",
    describe: (every) =>
      `Counts ${per(every)}: every strike a predator made at a prey in reach, and those that caught it. Strikes are dashed.`,
    series: [
      { column: "attempts", label: "strikes", colour: "--stain-ink-soft", dashed: true },
      { column: "captures", label: "captures", colour: "--predator" },
    ],
  },
];

/** Charts only a two-food world has (6.9), shown after the population chart. */
export const DIET_CHARTS: ChartSpec[] = [
  {
    id: "specialists",
    title: "Specialists",
    describe: () =>
      `Shares from 0 to 1 of the organisms alive: diet below ${SPECIALIST} eats mostly A, above ${1 - SPECIALIST} mostly B. Both rising together would be the population splitting; one alone, one kind taking over.`,
    series: [
      { column: "diet_low", label: "eats A", colour: "--food-a" },
      { column: "diet_high", label: "eats B", colour: "--food-b" },
      { column: "diet_sd", label: "diet spread (sd)", colour: "--stain-ink-soft", dashed: true },
    ],
    range: [0, 1],
  },
  {
    id: "foods",
    title: "Food by kind",
    describe: (every) =>
      `Food items of each kind on the plate, at the end of each ${every === 1 ? "tick" : `${every.toLocaleString("en")}-tick interval`}. The kind organisms eat less of piles up.`,
    series: [
      { column: "food_a", label: "A", colour: "--food-a" },
      { column: "food_b", label: "B", colour: "--food-b" },
    ],
  },
];

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

/** The phase plot (6.5), drawn by PhasePlot rather than TimeChart: its caption lives here with
 *  the other charts' so no copy sits in a component. */
export const PHASE_CHART = {
  id: "phase",
  title: "Prey against predators",
  describe:
    "The same two counts plotted against each other, one point per interval, joined in time order. Numbers that rise and fall in turn trace a loop; a line running into an axis is a species dying out. A pattern in this simulation, not a claim about real ecosystems.",
};

/** Which worlds a history describes. A world with predators has a predator count at every
 *  point (0 once they are extinct; null only without the section); a two-food world has a count
 *  of food A at every point. ``diet_sd`` is not the marker: it is null whenever nobody is
 *  alive, so a two-food world whose organisms died out would lose its diet charts. */
export function worldsOf(columns: HistoryColumns): { hunted: boolean; twoFoods: boolean } {
  return {
    hunted: columns.predators.some((v) => v !== null),
    twoFoods: columns.food_a.some((v) => v !== null),
  };
}

/** The charts for a history, in reading order: the population chart, then whatever the world
 *  has (predators, two foods), then the rest. The phase plot is shown separately when hunted. */
export function chartsFor(columns: HistoryColumns): ChartSpec[] {
  const { hunted, twoFoods } = worldsOf(columns);
  const extra = [...(hunted ? PREDATOR_CHARTS : []), ...(twoFoods ? DIET_CHARTS : [])];
  return [CHARTS[0]!, ...extra, ...CHARTS.slice(1)];
}

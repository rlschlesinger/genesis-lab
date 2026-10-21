// The API contract (docs/API.md, src/genesis/api/schemas.py) as TypeScript types.
// Kept in step with the server by fixtures the server writes (src/api/__fixtures__, built by
// scripts/build_api_fixtures.py and checked by tests on both sides).

export const API_VERSION = 1;
export const SNAPSHOT_VERSION = 2; // 2 (6.5): fullness, predators, captures

export type RunState = "idle" | "running" | "paused" | "completed" | "failed";

export interface Health {
  status: string;
  api_version: number;
  genesis_version: string;
}

export interface ConfigSummary {
  name: string;
  controller: string;
  max_ticks: number;
  initial_count: number;
  has_brains: boolean;
  mutation_enabled: boolean;
  has_predators: boolean;
  predator_controller: string | null;
  initial_predators: number | null;
}

export interface RunCreate {
  config?: string;
  seed?: number;
  max_ticks?: number;
  changes?: Record<string, unknown>;
}

export interface RunInfo {
  run_id: string;
  state: RunState;
  config_name: string;
  seed: number;
  controller: string;
  tick: number;
  max_ticks: number;
  /** Prey alive. */
  population: number;
  /** Predators alive; null in a world without predators. */
  predators: number | null;
  speed: number | null;
  viewers: number;
  error: string | null;
}

export interface BrainThought {
  tick: number;
  input_names: string[];
  inputs: number[];
  hidden_sum: number[];
  hidden: number[];
  output_sum: number[];
  outputs: number[];
  turn: number;
  throttle: number;
}

export type Species = "prey" | "predator";

export interface OrganismDetail {
  id: number;
  species: Species;
  alive: boolean;
  parent_id: number | null;
  founder_id: number;
  generation: number;
  birth_tick: number;
  death_tick: number | null;
  death_cause: string | null;
  age: number;
  energy: number;
  x: number;
  y: number;
  heading: number;
  food_eaten: number;
  /** Predators: prey caught. */
  prey_eaten: number;
  offspring_count: number;
  children: number[];
  genome: Record<string, number>;
  traits: Record<string, number>;
  brain_weights: Record<string, number> | null;
  thought: BrainThought | null;
}

export interface SavedRun {
  path: string;
  run_id: string;
  status: string;
  experiment_id: string | null;
  condition: string | null;
  seed: number;
  controller: string | null;
  ticks_run: number | null;
  final_population: number | null;
  started_at: string | null;
}

export interface ExportResult {
  run_id: string;
  path: string;
  ticks: number;
  digest: string;
  matches_live_run: boolean;
  ingested: boolean;
}

/** A live run's history as columns (docs/API.md, "History"): one point per `every` ticks. */
export interface HistoryColumns {
  tick: number[];
  population: number[];
  food_count: number[];
  lineages: number[];
  mean_energy: (number | null)[];
  /** Predators alive; null in a world without predators. */
  predators: (number | null)[];
  births: number[];
  deaths: number[];
  food_eaten: number[];
  /** Predator strikes, and those that caught their prey (0 without predators). */
  attempts: number[];
  captures: number[];
  toward_food: (number | null)[];
  mean_turn: (number | null)[];
  mean_throttle: (number | null)[];
}

export interface History {
  run_id: string;
  every: number;
  columns: HistoryColumns;
}

export interface LineageNode {
  id: number;
  generation: number;
  birth_tick: number;
  death_tick: number | null;
  alive: boolean;
  offspring_count: number;
  children: LineageNode[];
  hidden_children: number;
}

export interface Lineage {
  organism: LineageNode;
  ancestors: LineageNode[];
  descendants: number;
  founder_id: number;
  founder_family: number;
  founder_family_alive: number;
}

export interface LakeExperiment {
  experiment_id: string | null;
  title: string | null;
  runs: number;
}

export interface LakeRun {
  run_id: string;
  experiment_id: string | null;
  condition: string | null;
  seed: number;
  ticks_run: number;
  final_population: number;
  ticks_every: number;
  controller: string | null;
}

export interface LakeRunDetail extends LakeRun {
  config: Record<string, unknown>;
}

// --- The stream -----------------------------------------------------------------------------

export interface HelloMessage {
  type: "hello";
  version: number;
  run: RunInfo;
  world: { width: number; height: number };
}

export interface LastTick {
  births: number;
  deaths: number;
  food_eaten: number;
  mean_energy: number | null;
  lineages: number;
}

/** One column per organism field, all the same length, in organism-ID order. */
export interface OrganismColumns {
  id: number[];
  x: number[];
  y: number[];
  heading: number[];
  energy: number[];
  /** Energy as a share of the organism's reproduction threshold, 0-1: how full it's drawn. */
  fullness: number[];
  generation: number[];
  founder: number[];
}

/** Where a predator caught a prey (its position as it ate). */
export interface Capture {
  tick: number;
  x: number;
  y: number;
}

export interface Snapshot {
  type: "snapshot";
  version: number;
  run_id: string;
  tick: number;
  state: RunState;
  speed: number | null;
  error: string | null;
  population: number;
  last_tick: LastTick | null;
  food: { x: number[]; y: number[] };
  /** The prey (every organism in a world without predators). */
  organisms: OrganismColumns;
  /** Null in a world without predators. */
  predators: OrganismColumns | null;
  /** The latest captures, oldest first (a bounded number; none without predators). */
  captures: Capture[];
}

export interface GoneMessage {
  type: "gone";
  run_id: string;
  replaced_by: string | null;
}

export type ServerMessage = HelloMessage | Snapshot | GoneMessage;

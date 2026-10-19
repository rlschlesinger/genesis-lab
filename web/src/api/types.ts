// The API contract (docs/API.md, src/genesis/api/schemas.py) as TypeScript types.
// Kept in step with the server by fixtures the server writes (src/api/__fixtures__, built by
// scripts/build_api_fixtures.py and checked by tests on both sides).

export const API_VERSION = 1;
export const SNAPSHOT_VERSION = 1;

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
  population: number;
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

export interface OrganismDetail {
  id: number;
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

/** One column per organism field, all of length `population`, in organism-ID order. */
export interface OrganismColumns {
  id: number[];
  x: number[];
  y: number[];
  heading: number[];
  energy: number[];
  generation: number[];
  founder: number[];
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
  organisms: OrganismColumns;
}

export interface GoneMessage {
  type: "gone";
  run_id: string;
  replaced_by: string | null;
}

export type ServerMessage = HelloMessage | Snapshot | GoneMessage;

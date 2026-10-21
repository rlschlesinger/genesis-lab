// The TypeScript types must describe what the Python server actually sends.
//
// Two links make that a checked fact rather than a hope:
//   1. allKeys<T>(...) only compiles if it lists *every* field of type T, and no others
//      (checked by `npm run typecheck`).
//   2. Each list must equal the keys of a fixture the real server produced
//      (scripts/build_api_fixtures.py; tests/api/test_fixtures.py keeps those current).
// A field added, renamed or removed on either side breaks one of the two.

import { describe, expect, it } from "vitest";

import configs from "./__fixtures__/configs.json";
import gone from "./__fixtures__/gone.json";
import hello from "./__fixtures__/hello.json";
import history from "./__fixtures__/history.json";
import lakeExperiments from "./__fixtures__/lake_experiments.json";
import lakeRunDetail from "./__fixtures__/lake_run_detail.json";
import lakeRuns from "./__fixtures__/lake_runs.json";
import lakeSeries from "./__fixtures__/lake_series.json";
import lineage from "./__fixtures__/lineage.json";
import organism from "./__fixtures__/organism_detail.json";
import runInfo from "./__fixtures__/run_info.json";
import snapshot from "./__fixtures__/snapshot.json";
import predatorDetail from "./__fixtures__/organism_detail_predator.json";
import predatorHistory from "./__fixtures__/history_predators.json";
import huntedSnapshot from "./__fixtures__/snapshot_predators.json";
import dietDetail from "./__fixtures__/organism_detail_diet.json";
import dietHistory from "./__fixtures__/history_diets.json";
import dietSnapshot from "./__fixtures__/snapshot_diets.json";
import { parseServerMessage } from "./parse";
import type {
  BrainThought,
  Capture,
  ConfigSummary,
  GoneMessage,
  HelloMessage,
  History,
  HistoryColumns,
  LakeExperiment,
  LakeRun,
  LakeRunDetail,
  LastTick,
  Lineage,
  LineageNode,
  OrganismColumns,
  OrganismDetail,
  RunInfo,
  Snapshot,
} from "./types";

type Missing<T, K extends readonly PropertyKey[]> = Exclude<keyof T, K[number]>;

/** The keys of T, written out; a compile error if any is missing. */
function allKeys<T>() {
  return <const K extends readonly (keyof T)[]>(
    ...keys: K & ([Missing<T, K>] extends [never] ? unknown : ["missing keys:", Missing<T, K>])
  ): string[] => [...keys].map(String).sort();
}

const sortedKeys = (value: object) => Object.keys(value).sort();

describe("the TypeScript types match the server's real responses", () => {
  it("RunInfo", () => {
    expect(sortedKeys(runInfo)).toEqual(
      allKeys<RunInfo>()("run_id", "state", "config_name", "seed", "controller", "tick",
        "max_ticks", "population", "predators", "speed", "viewers", "error"),
    );
  });

  it("ConfigSummary", () => {
    expect(sortedKeys(configs[0]!)).toEqual(
      allKeys<ConfigSummary>()("name", "controller", "max_ticks", "initial_count", "has_brains",
        "mutation_enabled", "has_predators", "predator_controller", "initial_predators",
        "has_two_foods"),
    );
  });

  it("OrganismDetail and its brain thought", () => {
    expect(sortedKeys(organism)).toEqual(
      allKeys<OrganismDetail>()("id", "species", "alive", "parent_id", "founder_id", "generation",
        "birth_tick", "death_tick", "death_cause", "age", "energy", "x", "y", "heading",
        "food_eaten", "prey_eaten", "diet", "meals_b", "offspring_count", "children", "genome",
        "traits", "brain_weights", "thought"),
    );
    expect(sortedKeys(dietDetail)).toEqual(sortedKeys(organism));
    expect(typeof dietDetail.diet).toBe("number");
    expect(organism.diet).toBeNull();
    expect(sortedKeys(predatorDetail)).toEqual(sortedKeys(organism));
    expect(predatorDetail.species).toBe("predator");
    expect(predatorDetail.prey_eaten).toBeGreaterThan(0);
    expect(sortedKeys(organism.thought)).toEqual(
      allKeys<BrainThought>()("tick", "input_names", "inputs", "hidden_sum", "hidden",
        "output_sum", "outputs", "turn", "throttle"),
    );
    expect(organism.thought.inputs).toHaveLength(7);
    expect(organism.thought.hidden).toHaveLength(6);
    expect(organism.thought.outputs).toHaveLength(2);
    expect(Object.keys(organism.brain_weights)).toHaveLength(62);
  });

  it("History and its columns", () => {
    expect(sortedKeys(history)).toEqual(allKeys<History>()("run_id", "every", "columns"));
    expect(sortedKeys(history.columns)).toEqual(
      allKeys<HistoryColumns>()("tick", "population", "food_count", "lineages", "mean_energy",
        "predators", "food_a", "food_b", "diet_sd", "diet_low", "diet_high", "births", "deaths",
        "food_eaten", "attempts", "captures", "toward_food", "mean_turn", "mean_throttle"),
    );
    expect(sortedKeys(dietHistory.columns)).toEqual(sortedKeys(history.columns));
    expect(history.columns.diet_sd.every((v) => v === null)).toBe(true);
    expect(dietHistory.columns.diet_sd.every((v) => typeof v === "number")).toBe(true);
    expect(sortedKeys(predatorHistory.columns)).toEqual(sortedKeys(history.columns));
    expect(history.columns.predators.every((v) => v === null)).toBe(true);
    expect(predatorHistory.columns.predators.every((v) => typeof v === "number")).toBe(true);
    const lengths = new Set(Object.values(history.columns).map((c) => c.length));
    expect(lengths.size).toBe(1); // every column has one value per point
  });

  it("Lineage and its nodes", () => {
    expect(sortedKeys(lineage)).toEqual(
      allKeys<Lineage>()("organism", "ancestors", "descendants", "founder_id", "founder_family",
        "founder_family_alive"),
    );
    const nodeKeys = allKeys<LineageNode>()("id", "generation", "birth_tick", "death_tick", "alive",
      "offspring_count", "children", "hidden_children");
    expect(sortedKeys(lineage.organism)).toEqual(nodeKeys);
    expect(sortedKeys(lineage.organism.children[0]!)).toEqual(nodeKeys);
  });

  it("the lake views", () => {
    expect(sortedKeys(lakeExperiments[0]!)).toEqual(
      allKeys<LakeExperiment>()("experiment_id", "title", "runs"),
    );
    const runKeys = allKeys<LakeRun>()("run_id", "experiment_id", "condition", "seed", "ticks_run",
      "final_population", "ticks_every", "controller");
    expect(sortedKeys(lakeRuns[0]!)).toEqual(runKeys);
    expect(sortedKeys(lakeRunDetail)).toEqual(
      allKeys<LakeRunDetail>()("run_id", "experiment_id", "condition", "seed", "ticks_run",
        "final_population", "ticks_every", "controller", "config"),
    );
    expect(sortedKeys(lakeSeries)).toEqual(sortedKeys(history)); // the same shape as live history
    expect(sortedKeys(lakeSeries.columns)).toEqual(sortedKeys(history.columns));
  });

  it("the stream's hello, snapshot and gone messages", () => {
    expect(sortedKeys(hello)).toEqual(allKeys<HelloMessage>()("type", "version", "run", "world"));
    expect(sortedKeys(snapshot)).toEqual(
      allKeys<Snapshot>()("type", "version", "run_id", "tick", "state", "speed", "error",
        "population", "last_tick", "food", "diets", "organisms", "predators", "captures"),
    );
    expect(snapshot.food.kind).toBeNull();
    expect(snapshot.diets).toBeNull();
    expect(dietSnapshot.food.kind).toHaveLength(dietSnapshot.food.x.length);
    expect(dietSnapshot.diets).toHaveLength(dietSnapshot.population);
    const columns = allKeys<OrganismColumns>()("id", "x", "y", "heading", "energy", "fullness",
      "generation", "founder");
    expect(sortedKeys(snapshot.organisms)).toEqual(columns);
    expect(snapshot.predators).toBeNull();
    expect(sortedKeys(huntedSnapshot.predators)).toEqual(columns);
    expect(sortedKeys(huntedSnapshot.captures[0]!)).toEqual(allKeys<Capture>()("tick", "x", "y"));
    expect(sortedKeys(snapshot.last_tick)).toEqual(
      allKeys<LastTick>()("births", "deaths", "food_eaten", "mean_energy", "lineages"),
    );
    expect(sortedKeys(gone)).toEqual(allKeys<GoneMessage>()("type", "run_id", "replaced_by"));
  });

  it("every fixture message passes the runtime checks", () => {
    for (const message of [hello, snapshot, huntedSnapshot, dietSnapshot, gone]) {
      expect(parseServerMessage(JSON.stringify(message)).type).toBe(message.type);
    }
  });
});

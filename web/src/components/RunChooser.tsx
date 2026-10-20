import { useEffect } from "react";

import type { LakeExperiment } from "../api/types";
import { useLakeRuns } from "../hooks/useLake";
import styles from "./RunChooser.module.css";

export interface Choice {
  experimentId: string | null | undefined; // undefined: nothing chosen yet; null: no experiment
  runId: string | null;
}

/** Pick an experiment, then one of its runs. Runs are named by condition and seed, the two
 *  things that tell an experiment's runs apart. */
export function RunChooser({
  name,
  colour,
  experiments,
  choice,
  onChange,
  preferIndex,
}: {
  name: string;
  colour: "a" | "b";
  experiments: LakeExperiment[];
  choice: Choice;
  onChange(choice: Choice): void;
  preferIndex: number;
}) {
  const runs = useLakeRuns(choice.experimentId);

  // A sensible start: the first experiment, and a different run for A and B.
  useEffect(() => {
    if (choice.experimentId === undefined && experiments.length > 0) {
      onChange({ experimentId: experiments[0]!.experiment_id, runId: null });
    }
  }, [experiments, choice.experimentId, onChange]);
  useEffect(() => {
    if (choice.runId === null && runs.length > 0) {
      onChange({ ...choice, runId: runs[Math.min(preferIndex, runs.length - 1)]!.run_id });
    }
  }, [runs, choice, onChange, preferIndex]);

  return (
    <fieldset className={styles.chooser} data-colour={colour}>
      <legend className={styles.name}>Run {name}</legend>
      <label className={styles.field}>
        <span>Experiment</span>
        <select
          value={choice.experimentId ?? ""}
          onChange={(e) => onChange({ experimentId: e.target.value || null, runId: null })}
        >
          {experiments.map((x) => (
            <option key={x.experiment_id ?? ""} value={x.experiment_id ?? ""}>
              {x.experiment_id ?? "Saved from the lab"} ({x.runs} runs)
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span>Run</span>
        <select value={choice.runId ?? ""} onChange={(e) => onChange({ ...choice, runId: e.target.value || null })}>
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.condition ?? "run"}, seed {r.seed}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  );
}

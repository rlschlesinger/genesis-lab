import { type FormEvent, useState } from "react";

import { ApiError, api } from "../api/client";
import type { ConfigSummary } from "../api/types";
import { useServerLists } from "../hooks/useServerLists";
import { useLabStore } from "../store/labStore";
import styles from "./RunPicker.module.css";

function describe(c: ConfigSummary): string {
  const brains = c.has_brains ? "neural brains" : c.controller.replaceAll("_", " ");
  const evolving = c.mutation_enabled ? "evolving" : "no mutation";
  return `${c.initial_count} founders, ${brains}, ${evolving}, ${c.max_ticks.toLocaleString("en")} ticks`;
}

/** Start a run, or watch one the server already holds. Shown in place of the plate. */
export function RunPicker() {
  const { configs, runs, error: listError, refresh } = useServerLists();
  const watching = useLabStore((s) => s.runId);
  const [config, setConfig] = useState("neural");
  const [seed, setSeed] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = (e: FormEvent) => {
    e.preventDefault();
    const seedNumber = Number(seed);
    if (!Number.isInteger(seedNumber) || seedNumber < 0) {
      setError("The seed must be a whole number, 0 or more.");
      return;
    }
    setBusy(true);
    setError(null);
    api
      .createRun({ config, seed: seedNumber })
      .then((run) => useLabStore.getState().watchRun(run.run_id))
      .catch((err: unknown) => setError(err instanceof ApiError ? err.detail : String(err)))
      .finally(() => setBusy(false));
  };

  const remove = (runId: string) => {
    api
      .deleteRun(runId)
      .then(() => {
        if (runId === watching) useLabStore.getState().watchRun(null);
        refresh();
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.detail : String(err)));
  };

  return (
    <section className={styles.picker} aria-label="Choose a run">
      <form className={styles.start} onSubmit={start}>
        <h2 className={styles.title}>Start a run</h2>
        <label className={styles.field}>
          <span>Configuration</span>
          <select value={config} onChange={(e) => setConfig(e.target.value)}>
            {configs.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {configs.find((c) => c.name === config) && (
          <p className={styles.note}>{describe(configs.find((c) => c.name === config)!)}</p>
        )}
        <label className={styles.field}>
          <span>Seed</span>
          <input
            className="num"
            inputMode="numeric"
            value={seed}
            onChange={(e) => setSeed(e.target.value.trim())}
            aria-describedby="seed-note"
          />
        </label>
        <p id="seed-note" className={styles.note}>
          The same configuration and seed always produce the same run.
        </p>
        <button className={styles.primary} type="submit" disabled={busy || configs.length === 0}>
          {busy ? "Starting" : "Start run"}
        </button>
        {(error ?? listError) && (
          <p className={styles.error} role="alert">
            {error ?? listError}
          </p>
        )}
      </form>

      <div className={styles.live}>
        <h2 className={styles.title}>Runs on the server</h2>
        {runs.length === 0 ? (
          <p className={styles.note}>None yet. Live runs last until the server stops.</p>
        ) : (
          <ul className={styles.list}>
            {runs.map((r) => (
              <li key={r.run_id} className={styles.row} data-current={r.run_id === watching}>
                <span>
                  {r.config_name}, seed <span className="num">{r.seed}</span>
                </span>
                <span className={styles.meta}>
                  tick <span className="num">{r.tick.toLocaleString("en")}</span>, {r.state}
                </span>
                <span className={styles.actions}>
                  <button type="button" onClick={() => useLabStore.getState().watchRun(r.run_id)}>
                    {r.run_id === watching ? "Watching" : "Watch"}
                  </button>
                  <button type="button" onClick={() => remove(r.run_id)}>
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        {watching !== null && (
          <button className={styles.back} type="button" onClick={() => useLabStore.getState().setPicking(false)}>
            Back to the plate
          </button>
        )}
      </div>
    </section>
  );
}

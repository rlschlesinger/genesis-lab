import { useState } from "react";

import { ApiError, api } from "../api/client";
import { useLabStore } from "../store/labStore";
import styles from "./GoneNotice.module.css";

/** The watched run no longer exists (the server restarted, or someone removed it). Live
 *  runs live only in the server's memory; the same config and seed recreate it exactly. */
export function GoneNotice() {
  const status = useLabStore((s) => s.status);
  const run = useLabStore((s) => s.run);
  const [error, setError] = useState<string | null>(null);
  if (status !== "gone") return null;

  const again = () => {
    if (!run) return;
    api
      .createRun({ config: run.config_name, seed: run.seed })
      .then((fresh) => useLabStore.getState().watchRun(fresh.run_id))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : String(e)));
  };

  return (
    <div className={styles.notice} role="alert">
      <p>
        This run no longer exists on the server. Live runs are kept in memory, so they end when
        the server stops.
      </p>
      <div className={styles.actions}>
        {run && (
          <button type="button" onClick={again}>
            Start {run.config_name}, seed {run.seed} again
          </button>
        )}
        <button type="button" onClick={() => useLabStore.getState().setPicking(true)}>
          Choose another run
        </button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}

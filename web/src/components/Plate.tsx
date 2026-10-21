import type { CSSProperties } from "react";

import { useLabStore } from "../store/labStore";
import styles from "./Plate.module.css";
import { PlateCanvas } from "./PlateCanvas";
import { PlateSummary } from "./PlateSummary";

/** Grid spacing on the plate, in world units: the organisms' default sight range, so a cell
 *  is roughly what one founder can see across. The live canvas draws the same grid. */
const GRATICULE_UNITS = 20;

export function Plate() {
  const world = useLabStore((s) => s.world);
  const runId = useLabStore((s) => s.runId);
  const status = useLabStore((s) => s.status);
  const detail = useLabStore((s) => s.statusDetail);
  // Empty: neither species left (a world with predators runs on while either survives).
  const empty = useLabStore(
    (s) => s.snapshot !== null && s.snapshot.population === 0 && (s.snapshot.predators?.id.length ?? 0) === 0,
  );
  const ended = useLabStore((s) => s.snapshot?.state === "completed");
  const lastTick = useLabStore((s) => (s.snapshot ? s.snapshot.tick - 1 : 0));
  const width = world?.width ?? 200;
  const height = world?.height ?? 200;
  const style = {
    "--cell-x": `${(GRATICULE_UNITS / width) * 100}%`,
    "--cell-y": `${(GRATICULE_UNITS / height) * 100}%`,
    aspectRatio: `${width} / ${height}`,
  } as CSSProperties;

  return (
    <section className={styles.plate} style={style} data-live={world !== null} aria-label="The world">
      {world === null ? (
        <div className={styles.empty}>
          {status === "gone" || status === "error" ? (
            <>
              <p>
                {status === "gone"
                  ? "This run isn't on the server. Live runs end when the server stops, so an old link or bookmark can point at one that's gone."
                  : `This run's pictures can't be read: ${detail ?? "unknown problem"}.`}
              </p>
              <button type="button" className={styles.action} onClick={() => useLabStore.getState().setPicking(true)}>
                Choose a run
              </button>
            </>
          ) : (
            <p>{runId === null ? "Start a run to put a culture on the plate." : "Waiting for the first picture of this run."}</p>
          )}
        </div>
      ) : (
        <>
          <PlateCanvas world={world} />
          <PlateSummary />
          {empty && (
            <p className={`${styles.empty} ${styles.overlay}`} role="status">
              {ended
                ? `Extinct: the last organisms died on tick ${lastTick.toLocaleString("en")}. Reset to start the same world again, or save the run to study it.`
                : "No organisms are left. The world keeps ticking: food regrows, but nothing can be born."}
            </p>
          )}
        </>
      )}
    </section>
  );
}

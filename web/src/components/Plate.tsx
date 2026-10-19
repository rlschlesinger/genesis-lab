import type { CSSProperties } from "react";

import { useLabStore } from "../store/labStore";
import styles from "./Plate.module.css";

/** Grid spacing on the plate, in world units: the organisms' default sight range, so a cell
 *  is roughly what one founder can see across. */
const GRATICULE_UNITS = 20;

export function Plate() {
  const world = useLabStore((s) => s.world);
  const snapshot = useLabStore((s) => s.snapshot);
  const runId = useLabStore((s) => s.runId);
  const width = world?.width ?? 200;
  const height = world?.height ?? 200;
  const style = {
    "--cell-x": `${(GRATICULE_UNITS / width) * 100}%`,
    "--cell-y": `${(GRATICULE_UNITS / height) * 100}%`,
    aspectRatio: `${width} / ${height}`,
  } as CSSProperties;

  return (
    <section className={styles.plate} style={style} aria-label="The world">
      {snapshot === null && (
        <p className={styles.empty}>
          {runId === null
            ? "Start a run to put a culture on the plate."
            : "Waiting for the first picture of this run."}
        </p>
      )}
      {snapshot !== null && (
        <p className={styles.placeholder}>
          <span className="num">{snapshot.population}</span> organisms and{" "}
          <span className="num">{snapshot.food.x.length}</span> food items on the plate. Drawing
          them arrives in the next step.
        </p>
      )}
    </section>
  );
}

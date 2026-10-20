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
        <p className={styles.empty}>
          {runId === null
            ? "Start a run to put a culture on the plate."
            : "Waiting for the first picture of this run."}
        </p>
      ) : (
        <>
          <PlateCanvas world={world} />
          <PlateSummary />
        </>
      )}
    </section>
  );
}

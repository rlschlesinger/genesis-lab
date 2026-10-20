import type { CSSProperties } from "react";

import { useLabStore } from "../store/labStore";
import { Plate } from "./Plate";
import { RunPicker } from "./RunPicker";
import { SpecimenPanel } from "./SpecimenPanel";
import { StageBar } from "./StageBar";
import styles from "./WorldView.module.css";

/** The plate is the subject; the specimen panel and stage bar stay quiet around it. With no
 *  run (or "Change run"), the run picker takes the plate's place. */
export function WorldView() {
  const world = useLabStore((s) => s.world);
  const picking = useLabStore((s) => s.picking || s.runId === null);
  // The bench (plate + stage bar) is sized from the space available *and* the world's own
  // proportions, so the plate is never stretched: a world unit is the same length across
  // and down, as it is in the simulation.
  const aspect = world ? world.width / world.height : 1;
  return (
    <div className={styles.world}>
      {picking ? (
        <div className={styles.picker}>
          <RunPicker />
        </div>
      ) : (
        <div className={styles.bench} style={{ "--aspect": aspect } as CSSProperties}>
          <Plate />
          <StageBar />
        </div>
      )}
      <SpecimenPanel />
    </div>
  );
}

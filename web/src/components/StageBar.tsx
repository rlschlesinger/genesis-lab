import { useLabStore } from "../store/labStore";
import styles from "./StageBar.module.css";

/** Under the plate: where the run is, and how it's drawn. Run controls join it in 5.7. */
export function StageBar() {
  const snapshot = useLabStore((s) => s.snapshot);
  const run = useLabStore((s) => s.run);
  const showTrails = useLabStore((s) => s.showTrails);
  const setShowTrails = useLabStore((s) => s.setShowTrails);
  if (snapshot === null) return <div className={styles.stage} />;
  return (
    <div className={styles.stage}>
      <div className={styles.readout}>
        <span>
          Tick <span className={`num ${styles.figure}`}>{snapshot.tick.toLocaleString("en")}</span>
          {run && (
            <span className={styles.of}>
              {" "}
              of <span className="num">{run.max_ticks.toLocaleString("en")}</span>
            </span>
          )}
        </span>
        <span>
          <span className={`num ${styles.figure}`}>{snapshot.population}</span> alive
        </span>
        <span className={styles.state}>{snapshot.state}</span>
      </div>
      <div className={styles.view}>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={showTrails}
            onChange={(e) => setShowTrails(e.target.checked)}
          />
          Trails
        </label>
        <p className={styles.hint}>
          Drag to move, scroll to zoom, double-click to fit. Click an organism to examine it.
        </p>
      </div>
    </div>
  );
}

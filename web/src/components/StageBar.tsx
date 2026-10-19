import { useLabStore } from "../store/labStore";
import styles from "./StageBar.module.css";

/** Under the plate: where the run is. Controls join it in 5.7. */
export function StageBar() {
  const snapshot = useLabStore((s) => s.snapshot);
  const run = useLabStore((s) => s.run);
  if (snapshot === null) return <div className={styles.stage} />;
  return (
    <div className={styles.stage}>
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
  );
}

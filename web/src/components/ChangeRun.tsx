import { useLabStore } from "../store/labStore";
import styles from "./ChangeRun.module.css";

/** Opens the run picker over the plate (only while a run is being watched). */
export function ChangeRun() {
  const watching = useLabStore((s) => s.runId !== null);
  const picking = useLabStore((s) => s.picking);
  if (!watching || picking) return null;
  return (
    <button type="button" className={styles.change} onClick={() => useLabStore.getState().setPicking(true)}>
      Change run
    </button>
  );
}

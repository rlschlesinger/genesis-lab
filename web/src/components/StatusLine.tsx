import { STATUS_TEXT } from "../data/status";
import { useLabStore } from "../store/labStore";
import styles from "./StatusLine.module.css";

/** The connection, in words; the dot's colour repeats it for a glance, never alone. */
export function StatusLine() {
  const status = useLabStore((s) => s.status);
  const detail = useLabStore((s) => s.statusDetail);
  return (
    <span className={styles.status} data-status={status} role="status" aria-live="polite">
      <span className={styles.dot} aria-hidden="true" />
      {detail ?? STATUS_TEXT[status]}
    </span>
  );
}

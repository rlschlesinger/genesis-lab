import { useLabStore } from "../store/labStore";
import styles from "./SpecimenPanel.module.css";

/** One organism under examination. Filled in 5.7; until then, it says how to get there. */
export function SpecimenPanel() {
  const selected = useLabStore((s) => s.selectedOrganism);
  return (
    <aside className={styles.specimen} aria-label="Selected organism">
      <h2 className={styles.title}>{selected === null ? "No specimen" : `Organism ${selected}`}</h2>
      <p className={styles.hint}>
        Select an organism on the plate to see its genome, its family and what its brain is
        deciding.
      </p>
    </aside>
  );
}

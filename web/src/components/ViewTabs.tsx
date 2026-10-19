import { VIEWS } from "../data/views";
import { useLabStore } from "../store/labStore";
import styles from "./ViewTabs.module.css";

export function ViewTabs() {
  const view = useLabStore((s) => s.view);
  const setView = useLabStore((s) => s.setView);
  return (
    <nav aria-label="Views" className={styles.tabs}>
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          className={styles.tab}
          aria-current={v.id === view ? "page" : undefined}
          onClick={() => setView(v.id)}
        >
          {v.label}
        </button>
      ))}
    </nav>
  );
}

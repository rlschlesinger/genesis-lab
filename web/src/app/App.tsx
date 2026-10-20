import { AnalyticsView } from "../components/AnalyticsView";
import { EmptyView } from "../components/EmptyView";
import { Masthead } from "../components/Masthead";
import { WorldView } from "../components/WorldView";
import { VIEWS } from "../data/views";
import { useLabStore } from "../store/labStore";
import { useRunStream } from "../stream/useRunStream";
import styles from "./App.module.css";
import { useRunFromUrl } from "./useRunFromUrl";

export function App() {
  useRunFromUrl();
  useRunStream();
  const view = useLabStore((s) => s.view);
  const entry = VIEWS.find((v) => v.id === view);

  return (
    <div className={styles.lab}>
      <Masthead />
      <main className={styles.main} id="main">
        {view === "world" && <WorldView />}
        {view === "analytics" && <AnalyticsView />}
        {view !== "world" && view !== "analytics" && <EmptyView message={entry?.empty ?? ""} />}
      </main>
    </div>
  );
}

import { AnalyticsView } from "../components/AnalyticsView";
import { CompareView } from "../components/CompareView";
import { LineageView } from "../components/LineageView";
import { Masthead } from "../components/Masthead";
import { WorldView } from "../components/WorldView";
import { useLabStore } from "../store/labStore";
import { useRunStream } from "../stream/useRunStream";
import styles from "./App.module.css";
import { useRunFromUrl } from "./useRunFromUrl";

export function App() {
  useRunFromUrl();
  useRunStream();
  const view = useLabStore((s) => s.view);

  return (
    <div className={styles.lab}>
      <Masthead />
      <main className={styles.main} id="main">
        {view === "world" && <WorldView />}
        {view === "analytics" && <AnalyticsView />}
        {view === "compare" && <CompareView />}
        {view === "lineage" && <LineageView />}
      </main>
    </div>
  );
}

import { CHARTS } from "../data/charts";
import { useRunHistory } from "../hooks/useRunHistory";
import { useLabStore } from "../store/labStore";
import styles from "./AnalyticsView.module.css";
import { TimeChart } from "./TimeChart";

/** The watched run over time: small charts sharing one tick axis, each saying what it shows,
 *  in which unit, and what one point covers. */
export function AnalyticsView() {
  const run = useLabStore((s) => s.run);
  const runId = useLabStore((s) => s.runId);
  const { series, error } = useRunHistory();

  if (runId === null) {
    return <p className={styles.empty}>Start or watch a run on the World view; its charts appear here.</p>;
  }
  const points = series?.columns.tick.length ?? 0;
  return (
    <div className={styles.analytics}>
      <header className={styles.header}>
        <h2 className={styles.title}>{run ? `${run.config_name}, seed ${run.seed}` : "This run"}</h2>
        <p className={styles.meta}>
          {series && points > 0 ? (
            <>
              <span className="num">{points.toLocaleString("en")}</span> points, each covering{" "}
              <span className="num">{series.every.toLocaleString("en")}</span>{" "}
              {series.every === 1 ? "tick" : "ticks"}, up to tick{" "}
              <span className="num">{series.columns.tick[points - 1]!.toLocaleString("en")}</span>. Run{" "}
              <span className="num">{runId}</span>.
            </>
          ) : (
            "No ticks yet. Step or run it on the World view."
          )}
        </p>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
      </header>
      {series && points > 0 &&
        CHARTS.map((spec, i) => (
          <section key={spec.id} className={styles.chart} aria-labelledby={`chart-${spec.id}`}>
            <div className={styles.caption}>
              <h3 id={`chart-${spec.id}`} className={styles.chartTitle}>
                {spec.title}
              </h3>
              <p className={styles.describe}>{spec.describe(series.every)}</p>
            </div>
            <TimeChart
              series={spec.series}
              range={spec.range}
              data={[series.columns.tick, ...spec.series.map((s) => series.columns[s.column])]}
              showTicks={i === CHARTS.length - 1}
            />
          </section>
        ))}
    </div>
  );
}

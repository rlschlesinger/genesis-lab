import { useCallback, useState } from "react";

import { alignSeries } from "../compare/align";
import { configDiff } from "../compare/diff";
import { COMPARE_CHARTS, RUN_COLOURS } from "../data/compareCharts";
import { useLakeExperiments, useLakeRun } from "../hooks/useLake";
import styles from "./CompareView.module.css";
import { type Choice, RunChooser } from "./RunChooser";
import { TimeChart } from "./TimeChart";

const label = (data: ReturnType<typeof useLakeRun>, name: string) =>
  data.detail
    ? `${name}: ${data.detail.experiment_id ?? "saved"} ${data.detail.condition ?? "run"}, seed ${data.detail.seed}`
    : name;

/** Two finished runs from the data lake, side by side: what differs in their settings, then
 *  their charts on one tick axis. Run A in crystal violet, run B in iodine and dashed. */
export function CompareView() {
  const { experiments, error } = useLakeExperiments();
  const [a, setA] = useState<Choice>({ experimentId: undefined, runId: null });
  const [b, setB] = useState<Choice>({ experimentId: undefined, runId: null });
  const onA = useCallback((c: Choice) => setA(c), []);
  const onB = useCallback((c: Choice) => setB(c), []);
  const runA = useLakeRun(a.runId);
  const runB = useLakeRun(b.runId);

  if (error) {
    return (
      <p className={styles.empty} role="alert">
        {error}
      </p>
    );
  }
  const ready = runA.detail && runB.detail && runA.series && runB.series;
  const differences = ready ? configDiff(runA.detail!.config, runB.detail!.config) : [];
  return (
    <div className={styles.compare}>
      <div className={styles.choosers}>
        <RunChooser name="A" colour="a" experiments={experiments} choice={a} onChange={onA} preferIndex={0} />
        <RunChooser name="B" colour="b" experiments={experiments} choice={b} onChange={onB} preferIndex={1} />
      </div>

      {(runA.error || runB.error) && (
        <p className={styles.error} role="alert">
          {runA.error ?? runB.error}
        </p>
      )}

      {ready && (
        <>
          <section className={styles.differences} aria-label="What differs">
            <h2 className={styles.heading}>What differs</h2>
            {a.runId === b.runId ? (
              <p className={styles.note}>A and B are the same run.</p>
            ) : differences.length === 0 ? (
              <p className={styles.note}>The two runs have identical settings.</p>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">Setting</th>
                    <th scope="col">A</th>
                    <th scope="col">B</th>
                  </tr>
                </thead>
                <tbody>
                  {differences.map((d) => (
                    <tr key={d.path}>
                      <th scope="row" className="num">{d.path}</th>
                      <td className="num">{d.a}</td>
                      <td className="num">{d.b}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className={styles.note}>
              A ran <span className="num">{runA.detail!.ticks_run.toLocaleString("en")}</span> ticks
              (points of <span className="num">{runA.series!.every}</span>), B ran{" "}
              <span className="num">{runB.detail!.ticks_run.toLocaleString("en")}</span> (points of{" "}
              <span className="num">{runB.series!.every}</span>). Each run is one replicate: a
              difference between two runs is a hint, not evidence.
            </p>
          </section>

          {COMPARE_CHARTS.map((chart, i) => {
            const [ticks, va, vb] = alignSeries(runA.series!.columns, runB.series!.columns, chart.column);
            const rate = (values: (number | null)[], every: number) =>
              chart.perTick ? values.map((v) => (v === null ? null : v / every)) : values;
            return (
              <section key={chart.id} className={styles.chart}>
                <div className={styles.caption}>
                  <h3 className={styles.chartTitle}>{chart.title}</h3>
                  <p className={styles.note}>{chart.describe}</p>
                </div>
                <TimeChart
                  series={[
                    { label: label(runA, "A"), colour: RUN_COLOURS.a },
                    { label: label(runB, "B"), colour: RUN_COLOURS.b, dashed: true },
                  ]}
                  range={chart.range}
                  data={[ticks, rate(va, runA.series!.every), rate(vb, runB.series!.every)]}
                  showTicks={i === COMPARE_CHARTS.length - 1}
                />
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}

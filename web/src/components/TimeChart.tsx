import "uplot/dist/uPlot.min.css";

import { useEffect, useRef } from "react";
import uPlot from "uplot";

import { type TokenName, token } from "../styles/tokens";
import styles from "./TimeChart.module.css";

const HEIGHT = 170;

export interface SeriesStyle {
  label: string;
  colour: TokenName;
  dashed?: boolean | undefined;
}

export interface TimeChartProps {
  series: SeriesStyle[];
  /** First array: ticks; then one array per series (null = a gap). */
  data: (number | null)[][];
  range?: [number, number] | undefined;
  showTicks: boolean;
}

function showLatest(u: uPlot): void {
  const n = u.data[0]?.length ?? 0;
  if ((u.cursor.left ?? -1) < 0 && n > 0) u.setLegend({ idx: n - 1 });
}

function options(props: TimeChartProps, width: number): uPlot.Options {
  const font = `12px ${token("--font")}`;
  const axis = {
    stroke: token("--stain-ink-soft"),
    font,
    grid: { stroke: token("--graticule"), width: 1 },
    ticks: { stroke: token("--graticule"), width: 1 },
  };
  return {
    width,
    height: HEIGHT,
    cursor: { drag: { x: false, y: false } },
    legend: { show: true, live: true },
    // Not hovering: the legend shows the latest values (what a live run asks). Done in uPlot's
    // own hooks because it draws asynchronously: a call made before its first draw is lost.
    hooks: { draw: [showLatest], setCursor: [showLatest] },
    scales: {
      x: { time: false },
      y: props.range
        ? { range: props.range }
        : { range: (_u, min, max) => [Math.min(0, min), max > 0 ? max * 1.08 : 1] },
    },
    // Small multiples share one tick axis: only the bottom chart labels it; the others keep
    // the gridlines so the eye can line up across charts.
    axes: [
      props.showTicks ? { ...axis, label: "tick", labelFont: font } : { ...axis, size: 8, values: () => [] },
      { ...axis, size: 52 },
    ],
    series: [
      { label: "tick" },
      ...props.series.map((s) => ({
        label: s.label,
        stroke: token(s.colour),
        width: 1.6,
        spanGaps: false, // a gap (nothing to measure, or no point there) stays a gap
        ...(s.dashed ? { dash: [4, 3] } : {}),
      })),
    ],
  };
}

/** One small chart against ticks. uPlot draws on a canvas; the legend under it shows the
 *  values under the cursor, or the latest values when the pointer is elsewhere. */
export function TimeChart(props: TimeChartProps) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const shape = `${props.showTicks}|${props.range ?? ""}|${props.series.map((s) => `${s.label}:${s.colour}:${s.dashed ?? ""}`).join(",")}`;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const created = new uPlot(options(props, element.clientWidth || 600), props.data as uPlot.AlignedData, element);
    plot.current = created;
    const resize = new ResizeObserver(() => created.setSize({ width: element.clientWidth, height: HEIGHT }));
    resize.observe(element);
    return () => {
      resize.disconnect();
      created.destroy();
      plot.current = null;
    };
    // Rebuilt only when what is drawn changes (series, range, axis); data goes through setData.
  }, [shape]);

  useEffect(() => {
    const p = plot.current;
    if (!p) return;
    p.setData(props.data as uPlot.AlignedData);
  });

  return <div ref={host} className={styles.chart} />;
}

import "uplot/dist/uPlot.min.css";

import { useEffect, useRef } from "react";
import uPlot from "uplot";

import type { HistoryColumns } from "../api/types";
import type { ChartSpec } from "../data/charts";
import { token } from "../styles/tokens";
import styles from "./TimeChart.module.css";

const HEIGHT = 170;

function options(spec: ChartSpec, width: number, showTicks: boolean): uPlot.Options {
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
    scales: {
      x: { time: false },
      y: spec.range ? { range: spec.range } : { range: (_u, min, max) => [Math.min(0, min), max > 0 ? max * 1.08 : 1] },
    },
    // Small multiples share one tick axis: only the bottom chart labels it; the others keep
    // the gridlines so the eye can line up across charts.
    axes: [
      showTicks ? { ...axis, label: "tick", labelFont: font } : { ...axis, size: 8, values: () => [] },
      { ...axis, size: 48 },
    ],
    series: [
      { label: "tick" },
      ...spec.series.map((s) => ({
        label: s.label,
        stroke: token(s.colour),
        width: 1.6,
        spanGaps: false, // a gap (nothing to measure) stays a gap; it isn't drawn as a line
        ...(s.dashed ? { dash: [4, 3] } : {}),
      })),
    ],
  };
}

/** One small chart against ticks, from history columns. uPlot draws on a canvas; the legend
 *  under it shows the values under the cursor. */
export function TimeChart({
  spec,
  columns,
  showTicks,
}: {
  spec: ChartSpec;
  columns: HistoryColumns;
  showTicks: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const data = (): uPlot.AlignedData => [columns.tick, ...spec.series.map((s) => columns[s.column])] as uPlot.AlignedData;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const created = new uPlot(options(spec, element.clientWidth || 600, showTicks), data(), element);
    plot.current = created;
    const resize = new ResizeObserver(() => created.setSize({ width: element.clientWidth, height: HEIGHT }));
    resize.observe(element);
    return () => {
      resize.disconnect();
      created.destroy();
      plot.current = null;
    };
    // The plot is rebuilt only for a different chart; new data goes through setData below.
  }, [spec, showTicks]);

  useEffect(() => {
    const p = plot.current;
    if (!p) return;
    p.setData(data());
    // Not hovering: the legend shows the latest values, which is what a live run asks.
    if ((p.cursor.left ?? -1) < 0 && columns.tick.length > 0) p.setLegend({ idx: columns.tick.length - 1 });
  });

  return <div ref={host} className={styles.chart} />;
}

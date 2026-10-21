import type { HistoryColumns } from "../api/types";
import { PHASE_BOX as BOX, phaseGeometry } from "../data/phase";
import styles from "./PhasePlot.module.css";

/** Prey against predators over the run: a predator-prey cycle draws a loop, a collapse a
 *  line into an axis. Drawn in SVG from the same history as the charts above it. */
export function PhasePlot({ columns }: { columns: HistoryColumns }) {
  const g = phaseGeometry(columns.population, columns.predators, BOX);
  const right = BOX.width - BOX.right;
  const bottom = BOX.height - BOX.bottom;
  const summary = g.end
    ? `Prey against predators over ${columns.tick.length.toLocaleString("en")} points, from the start (open circle) to now (filled).`
    : "No predator counts yet.";
  return (
    <figure className={styles.phase}>
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} role="img" aria-label={summary}>
        <line x1={BOX.left} y1={bottom} x2={right} y2={bottom} className={styles.axis} />
        <line x1={BOX.left} y1={BOX.top} x2={BOX.left} y2={bottom} className={styles.axis} />
        <text x={BOX.left} y={bottom + 16} className={styles.tick}>0</text>
        <text x={right} y={bottom + 16} className={styles.tick} textAnchor="end">{g.preyMax}</text>
        <text x={(BOX.left + right) / 2} y={BOX.height - 4} className={styles.label} textAnchor="middle">
          prey alive
        </text>
        <text x={BOX.left - 6} y={BOX.top + 10} className={styles.tick} textAnchor="end">{g.predatorMax}</text>
        <text
          x={12}
          y={(BOX.top + bottom) / 2}
          className={styles.label}
          textAnchor="middle"
          transform={`rotate(-90 12 ${(BOX.top + bottom) / 2})`}
        >
          predators alive
        </text>
        <polyline points={g.points} className={styles.path} />
        {g.start && <circle cx={g.start.x} cy={g.start.y} r={4} className={styles.start} />}
        {g.end && <circle cx={g.end.x} cy={g.end.y} r={4} className={styles.end} />}
      </svg>
      <figcaption className={styles.caption}>{summary}</figcaption>
    </figure>
  );
}

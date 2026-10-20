import type { BrainThought } from "../api/types";
import { INPUT_LABELS, shade, signal, turnPhrase } from "../data/brain";
import styles from "./BrainDiagram.module.css";

const W = 300;
const H = 214;
const COLUMN = { input: 104, hidden: 184, output: 250 };
const R = 8;

function rows(count: number): number[] {
  const top = 16;
  const step = (H - 2 * top) / Math.max(1, count - 1);
  return Array.from({ length: count }, (_, i) => top + i * step);
}

function weight(weights: Record<string, number>, name: string): number {
  return weights[name] ?? 0;
}

/** The network on its latest decision: 7 inputs, 6 hidden units, 2 outputs. Nodes are shaded
 *  by their value (violet positive, safranin negative); each line by what it carried into the
 *  next unit (weight x the value feeding it). The same numbers are written out below it. */
export function BrainDiagram({ thought, weights }: { thought: BrainThought; weights: Record<string, number> }) {
  const inY = rows(thought.inputs.length);
  const hidY = rows(thought.hidden.length);
  const outY = [H / 2 - 40, H / 2 + 40];
  const [turnRaw, throttle] = thought.outputs;
  const summary = `On tick ${thought.tick} it turned ${turnPhrase(thought.turn)} at ${Math.round(thought.throttle * 100)}% throttle.`;

  const line = (key: string, x1: number, y1: number, x2: number, y2: number, value: number) => {
    const s = shade(value);
    return (
      <line
        key={key}
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        className={styles[s.colour]}
        strokeOpacity={0.08 + 0.8 * s.strength}
        strokeWidth={0.6 + 1.8 * s.strength}
      />
    );
  };
  const node = (key: string, x: number, y: number, value: number) => {
    const s = shade(value);
    return (
      <circle key={key} cx={x} cy={y} r={R} className={`${styles.node} ${styles[s.colour]}`}
        fillOpacity={0.12 + 0.88 * s.strength} />
    );
  };

  return (
    <figure className={styles.brain}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
        {thought.hidden.map((_, h) =>
          thought.input_names.map((name, i) =>
            line(`ih${i}-${h}`, COLUMN.input, inY[i]!, COLUMN.hidden, hidY[h]!,
              signal(weight(weights, `wh_${h}_${name}`), thought.inputs[i]!)),
          ),
        )}
        {["turn", "throttle"].map((out, o) =>
          thought.hidden.map((value, h) =>
            line(`ho${h}-${o}`, COLUMN.hidden, hidY[h]!, COLUMN.output, outY[o]!,
              signal(weight(weights, `wo_${out}_${h}`), value)),
          ),
        )}
        {thought.input_names.map((name, i) => (
          <g key={name}>
            <text x={COLUMN.input - R - 6} y={inY[i]! + 4} className={styles.label} textAnchor="end">
              {INPUT_LABELS[name] ?? name}
            </text>
            {node(name, COLUMN.input, inY[i]!, thought.inputs[i]!)}
          </g>
        ))}
        {thought.hidden.map((value, h) => node(`h${h}`, COLUMN.hidden, hidY[h]!, value))}
        {node("turn", COLUMN.output, outY[0]!, turnRaw ?? 0)}
        {node("throttle", COLUMN.output, outY[1]!, (throttle ?? 0) * 2 - 1)}
        <text x={COLUMN.output} y={outY[0]! - 14} className={styles.label} textAnchor="middle">turn</text>
        <text x={COLUMN.output} y={outY[1]! + 24} className={styles.label} textAnchor="middle">throttle</text>
      </svg>
      <figcaption className={styles.caption}>
        <p>{summary}</p>
        <dl className={styles.values}>
          {thought.input_names.map((name, i) => (
            <div key={name}>
              <dt>{INPUT_LABELS[name] ?? name}</dt>
              <dd className="num">{thought.inputs[i]!.toFixed(2)}</dd>
            </div>
          ))}
        </dl>
      </figcaption>
    </figure>
  );
}

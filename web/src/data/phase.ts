// The phase plot (6.5): prey against predators, one point per history point, joined in time
// order. Pure geometry, so it can be tested without drawing anything.

export interface PhaseGeometry {
  /** SVG polyline points, "x,y x,y ...", in the plot's own coordinates. */
  points: string;
  start: { x: number; y: number } | null;
  end: { x: number; y: number } | null;
  /** The axes' top values: round numbers at or above the largest count. */
  preyMax: number;
  predatorMax: number;
}

export interface PhaseBox {
  width: number;
  height: number;
  /** Space left of and below the plot for the axis labels. */
  left: number;
  bottom: number;
  top: number;
  right: number;
}

/** The smallest of 1, 2, 5, 10, 20, 50 ... at or above ``value`` (and at least 5). */
export function niceMax(value: number): number {
  const target = Math.max(5, value);
  for (let scale = 1; ; scale *= 10) {
    for (const step of [1, 2, 5]) if (step * scale >= target) return step * scale;
  }
}

/** Points where both counts are known (a world without predators has none). Prey run along
 *  x from the left, predators up y from the bottom, both from 0. */
export function phaseGeometry(
  prey: readonly (number | null)[],
  predators: readonly (number | null)[],
  box: PhaseBox,
): PhaseGeometry {
  const pairs: [number, number][] = [];
  for (let i = 0; i < Math.min(prey.length, predators.length); i++) {
    const a = prey[i];
    const b = predators[i];
    if (a != null && b != null) pairs.push([a, b]);
  }
  const preyMax = niceMax(Math.max(0, ...pairs.map((p) => p[0])));
  const predatorMax = niceMax(Math.max(0, ...pairs.map((p) => p[1])));
  const w = box.width - box.left - box.right;
  const h = box.height - box.top - box.bottom;
  const place = ([a, b]: [number, number]) => ({
    x: box.left + (a / preyMax) * w,
    y: box.top + h - (b / predatorMax) * h,
  });
  const placed = pairs.map(place);
  return {
    points: placed.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
    start: placed[0] ?? null,
    end: placed[placed.length - 1] ?? null,
    preyMax,
    predatorMax,
  };
}

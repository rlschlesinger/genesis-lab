// Which organism did the user click? The nearest one to the click, if it is close enough.

import type { Point } from "./camera";
import type { Pose } from "./interpolate";

export function nearestOrganism(
  poses: ReadonlyMap<number, Pose>,
  at: Point,
  maxDistance: number,
): number | null {
  let best: number | null = null;
  let bestDistance = maxDistance;
  for (const [id, pose] of poses) {
    const d = Math.hypot(pose.x - at.x, pose.y - at.y);
    if (d <= bestDistance) {
      best = id;
      bestDistance = d;
    }
  }
  return best;
}

/** Keyboard selection: the next (+1) or previous (-1) organism by ID, wrapping around. If the
 *  current one has died, its neighbours by ID are still the natural next and previous. */
export function stepSelection(ids: readonly number[], current: number | null, direction: 1 | -1): number | null {
  const sorted = [...ids].sort((a, b) => a - b);
  const n = sorted.length;
  if (n === 0) return null;
  if (current === null) return direction === 1 ? sorted[0]! : sorted[n - 1]!;
  const i = sorted.indexOf(current);
  if (i !== -1) return sorted[(i + direction + n) % n]!;
  if (direction === 1) return sorted.find((id) => id > current) ?? sorted[0]!;
  const smaller = sorted.filter((id) => id < current);
  return smaller.length > 0 ? smaller[smaller.length - 1]! : sorted[n - 1]!;
}

// Gliding between snapshots. The server sends ~15 pictures a second; drawn as they come,
// organisms would jump. Instead each frame draws them part of the way from where they were
// last drawn to where the newest snapshot puts them. This is display only: the positions
// the simulation uses never pass through here.

import type { OrganismColumns } from "../api/types";

export interface Pose {
  x: number;
  y: number;
  heading: number;
}

/** Further than this (world units) between two pictures is a jump, not a glide: a reset or
 *  a very fast run. Drawing a glide across the world would be misleading, so it snaps. */
export const SNAP_DISTANCE = 15;

/** The shortest signed turn from angle a to angle b, in (-pi, pi]. */
export function angleDelta(a: number, b: number): number {
  let d = (b - a) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d <= -Math.PI) d += 2 * Math.PI;
  return d;
}

/** Each organism of ``next``, posed ``t`` (0..1) of the way from ``from`` (the poses on screen
 *  now). Newborns appear where they are; the dead simply aren't in ``next``. */
export function blend(from: ReadonlyMap<number, Pose>, next: OrganismColumns, t: number): Map<number, Pose> {
  const out = new Map<number, Pose>();
  const s = Math.min(1, Math.max(0, t));
  for (let i = 0; i < next.id.length; i++) {
    const id = next.id[i]!;
    const target = { x: next.x[i]!, y: next.y[i]!, heading: next.heading[i]! };
    const start = from.get(id);
    if (!start || Math.hypot(target.x - start.x, target.y - start.y) > SNAP_DISTANCE) {
      out.set(id, target);
      continue;
    }
    out.set(id, {
      x: start.x + (target.x - start.x) * s,
      y: start.y + (target.y - start.y) * s,
      heading: start.heading + angleDelta(start.heading, target.heading) * s,
    });
  }
  return out;
}

/** How far through the glide we are: elapsed time over the expected gap between pictures. */
export function progress(elapsedMs: number, intervalMs: number, reducedMotion: boolean): number {
  if (reducedMotion || intervalMs <= 0) return 1;
  return Math.min(1, Math.max(0, elapsedMs / intervalMs));
}

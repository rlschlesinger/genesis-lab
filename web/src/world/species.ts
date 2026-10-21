// How each species is drawn, and the timing of capture marks. Pure rules, kept apart from the
// renderer so they can be read and tested without a GPU. Colours are not here: they come
// from the CSS tokens (--prey, --predator), as everywhere in the lab.

import type { Capture, Snapshot } from "../api/types";

export type SpeciesName = "prey" | "predator";

export interface Body {
  /** Drawn radius in world units when zoomed in (a prey eats within 2, a predator strikes
   *  within 3: bodies stay smaller than their reach, so contact is visible). */
  units: number;
  /** Never smaller than this on screen, however far out. */
  minPx: number;
}

export const BODIES: Record<SpeciesName, Body> = {
  prey: { units: 1.3, minPx: 3.5 },
  predator: { units: 2.0, minPx: 5.5 },
};

/** How opaque a cell's interior is drawn for its fullness (energy over its reproduction
 *  threshold, 0-1). Never fully clear, so a starving cell is pale but still visible; a cell
 *  ready to divide is solid. */
export function interiorAlpha(fullness: number): number {
  const f = Math.min(1, Math.max(0, fullness));
  return 0.15 + 0.85 * f;
}

/** How long a capture stays marked on the plate, in milliseconds of real time. Real time,
 *  not ticks: at hundreds of ticks a second a mark measured in ticks would never be seen. */
export const MARK_MS = 1200;

export interface MarkLook {
  alpha: number;
  /** Ring radius in world units. */
  radius: number;
}

/** A capture mark ``ageMs`` after it appeared: a ring that widens a little and fades. With
 *  reduced motion it doesn't change at all, then disappears. Null once it has expired. */
export function markLook(ageMs: number, reducedMotion: boolean): MarkLook | null {
  if (ageMs < 0 || ageMs >= MARK_MS) return null;
  if (reducedMotion) return { alpha: 0.7, radius: 3 };
  const t = ageMs / MARK_MS;
  return { alpha: 0.85 * (1 - t), radius: 2 + 2.5 * t };
}

/** Whether ``next`` is the first picture of another run than ``previous``: a different run ID
 *  (a reset followed through ``gone.replaced_by``), or time running backwards (the same ID can't
 *  do that; a lower tick is a fresh run of a stream that reconnected before the ID changed).
 *  Nothing from the old run (trails, marks, the newest capture seen) may carry over. Checking
 *  the tick alone misses a replacement that has already run past the old run's tick. */
export function startsNewRun(previous: Pick<Snapshot, "run_id" | "tick"> | null, next: Pick<Snapshot, "run_id" | "tick">): boolean {
  return previous !== null && (next.run_id !== previous.run_id || next.tick < previous.tick);
}

/** The captures in ``captures`` newer than ``seenUpTo`` (the newest tick already marked). A
 *  snapshot repeats recent captures; marking each only once is the viewer's job. */
export function newCaptures(captures: readonly Capture[], seenUpTo: number): Capture[] {
  return captures.filter((c) => c.tick > seenUpTo);
}

/** A colour ``t`` (0-1) of the way from ``a`` to ``b``, each channel mixed in sRGB and
 *  rounded. Two foods (6.9): an organism's diet places it between the two foods' stains. */
export function mixColour(a: number, b: number, t: number): number {
  const s = Math.min(1, Math.max(0, t));
  const channel = (shift: number) => {
    const x = (a >> shift) & 0xff;
    const y = (b >> shift) & 0xff;
    return Math.round(x + (y - x) * s) << shift;
  };
  return (channel(16) | channel(8) | channel(0)) >>> 0;
}

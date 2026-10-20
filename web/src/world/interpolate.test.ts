import { describe, expect, it } from "vitest";

import type { OrganismColumns } from "../api/types";
import { SNAP_DISTANCE, angleDelta, blend, progress, type Pose } from "./interpolate";

function columns(rows: Array<[number, number, number, number]>): OrganismColumns {
  return {
    id: rows.map((r) => r[0]),
    x: rows.map((r) => r[1]),
    y: rows.map((r) => r[2]),
    heading: rows.map((r) => r[3]),
    energy: rows.map(() => 10),
    generation: rows.map(() => 0),
    founder: rows.map((r) => r[0]),
  };
}

describe("gliding between pictures", () => {
  it("moves part of the way, by the shortest turn", () => {
    const from = new Map<number, Pose>([[1, { x: 0, y: 0, heading: 3.0 }]]);
    const half = blend(from, columns([[1, 4, 2, -3.0]]), 0.5).get(1)!;
    expect(half.x).toBe(2);
    expect(half.y).toBe(1);
    // 3.0 to -3.0 rad is a small turn through pi (0.28 rad), not a 6 rad spin the long way.
    expect(Math.abs(angleDelta(3.0, -3.0))).toBeCloseTo(2 * Math.PI - 6, 9);
    expect(half.heading).toBeCloseTo(3.0 + (2 * Math.PI - 6) / 2, 9);
  });

  it("puts newborns where they are and drops the dead", () => {
    const from = new Map<number, Pose>([[1, { x: 0, y: 0, heading: 0 }], [2, { x: 5, y: 5, heading: 0 }]]);
    const poses = blend(from, columns([[1, 1, 0, 0], [3, 50, 60, 1]]), 0.25);
    expect([...poses.keys()]).toEqual([1, 3]);
    expect(poses.get(3)).toEqual({ x: 50, y: 60, heading: 1 });
  });

  it("snaps instead of gliding across the world", () => {
    const from = new Map<number, Pose>([[1, { x: 0, y: 0, heading: 0 }]]);
    const far = SNAP_DISTANCE + 1;
    expect(blend(from, columns([[1, far, 0, 0]]), 0.1).get(1)!.x).toBe(far);
  });

  it("reaches the picture exactly, and skips gliding with reduced motion", () => {
    expect(progress(100, 66, false)).toBe(1);
    expect(progress(33, 66, false)).toBe(0.5);
    expect(progress(0, 66, true)).toBe(1);
  });
});

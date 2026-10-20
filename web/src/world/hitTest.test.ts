import { describe, expect, it } from "vitest";

import { nearestOrganism, stepSelection } from "./hitTest";
import type { Pose } from "./interpolate";

const poses = new Map<number, Pose>([
  [4, { x: 10, y: 10, heading: 0 }],
  [9, { x: 12, y: 10, heading: 0 }],
  [20, { x: 100, y: 100, heading: 0 }],
]);

describe("selecting organisms", () => {
  it("picks the nearest organism within reach, or none", () => {
    expect(nearestOrganism(poses, { x: 11.5, y: 10 }, 3)).toBe(9);
    expect(nearestOrganism(poses, { x: 10.2, y: 10 }, 3)).toBe(4);
    expect(nearestOrganism(poses, { x: 50, y: 50 }, 3)).toBeNull();
  });

  it("steps through organisms by ID with the keyboard, wrapping around", () => {
    const ids = [20, 4, 9];
    expect(stepSelection(ids, null, 1)).toBe(4);
    expect(stepSelection(ids, null, -1)).toBe(20);
    expect(stepSelection(ids, 9, 1)).toBe(20);
    expect(stepSelection(ids, 20, 1)).toBe(4);
    expect(stepSelection(ids, 4, -1)).toBe(20);
    expect(stepSelection(ids, 7, 1)).toBe(9); // 7 has died: its neighbours by ID
    expect(stepSelection(ids, 7, -1)).toBe(4);
    expect(stepSelection([], 4, 1)).toBeNull();
  });
});

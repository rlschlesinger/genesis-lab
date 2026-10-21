import { describe, expect, it } from "vitest";

import { BODIES, MARK_MS, interiorAlpha, markLook, newCaptures } from "./species";

describe("drawing rules for two species", () => {
  it("draws predators larger than prey, and both smaller than their reach", () => {
    expect(BODIES.predator.units).toBeGreaterThan(BODIES.prey.units);
    expect(BODIES.prey.units).toBeLessThan(2); // prey eat within 2 units
    expect(BODIES.predator.units).toBeLessThan(3); // predators strike within 3
  });

  it("fills a cell by how much energy it has, never quite clear", () => {
    expect(interiorAlpha(0)).toBeCloseTo(0.15);
    expect(interiorAlpha(1)).toBe(1);
    expect(interiorAlpha(0.5)).toBeCloseTo(0.575);
    expect(interiorAlpha(-3)).toBe(interiorAlpha(0));
    expect(interiorAlpha(7)).toBe(1);
  });

  it("fades a capture mark out over its lifetime", () => {
    const start = markLook(0, false)!;
    const later = markLook(MARK_MS / 2, false)!;
    expect(later.alpha).toBeLessThan(start.alpha);
    expect(later.radius).toBeGreaterThan(start.radius);
    expect(markLook(MARK_MS, false)).toBeNull();
    expect(markLook(-1, false)).toBeNull();
  });

  it("holds a capture mark still with reduced motion, then removes it", () => {
    expect(markLook(0, true)).toEqual(markLook(MARK_MS - 1, true));
    expect(markLook(MARK_MS, true)).toBeNull();
  });

  it("marks each capture once, however many snapshots repeat it", () => {
    const captures = [
      { tick: 10, x: 1, y: 1 },
      { tick: 12, x: 2, y: 2 },
      { tick: 12, x: 3, y: 3 },
    ];
    expect(newCaptures(captures, 0)).toHaveLength(3);
    expect(newCaptures(captures, 10)).toEqual(captures.slice(1));
    expect(newCaptures(captures, 12)).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";

import { BODIES, MARK_MS, interiorAlpha, markLook, mixColour, newCaptures, startsNewRun } from "./species";

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

describe("tinting by diet", () => {
  it("runs from one food's stain to the other's", () => {
    const iodine = 0xa9741a;
    const malachite = 0x2e7d5b;
    expect(mixColour(iodine, malachite, 0)).toBe(iodine);
    expect(mixColour(iodine, malachite, 1)).toBe(malachite);
    expect(mixColour(0x000000, 0xffffff, 0.5)).toBe(0x808080);
    expect(mixColour(iodine, malachite, -1)).toBe(iodine);
  });
});

describe("telling a new run from the next picture of the same one", () => {
  const a5 = { run_id: "a", tick: 5 };
  it("is not a new run on the first picture, or when the same run moves on or repeats", () => {
    expect(startsNewRun(null, a5)).toBe(false);
    expect(startsNewRun(a5, { run_id: "a", tick: 6 })).toBe(false);
    expect(startsNewRun(a5, { run_id: "a", tick: 5 })).toBe(false);
  });
  it("is a new run when time goes backwards, or when the run ID changes at any tick", () => {
    expect(startsNewRun(a5, { run_id: "a", tick: 0 })).toBe(true);
    expect(startsNewRun(a5, { run_id: "b", tick: 0 })).toBe(true);
    // A replacement followed after a long disconnection may already be past the old tick.
    expect(startsNewRun(a5, { run_id: "b", tick: 900 })).toBe(true);
  });
});

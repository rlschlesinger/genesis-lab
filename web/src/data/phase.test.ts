import { describe, expect, it } from "vitest";

import { niceMax, phaseGeometry } from "./phase";

const box = { width: 200, height: 120, left: 40, bottom: 20, top: 0, right: 0 };

describe("the phase plot's geometry", () => {
  it("rounds axis tops up to 1, 2 or 5 times a power of ten", () => {
    expect([niceMax(0), niceMax(3), niceMax(7), niceMax(12), niceMax(130), niceMax(500)]).toEqual([
      5, 5, 10, 20, 200, 500,
    ]);
  });

  it("puts prey along x and predators up y, from 0 at the corner", () => {
    const g = phaseGeometry([0, 100, 200], [0, 10, 20], box);
    expect(g.preyMax).toBe(200);
    expect(g.predatorMax).toBe(20);
    expect(g.start).toEqual({ x: 40, y: 100 }); // bottom left
    expect(g.end).toEqual({ x: 200, y: 0 }); // top right
    expect(g.points.split(" ")).toHaveLength(3);
  });

  it("skips points where either count is unknown, and draws nothing without predators", () => {
    expect(phaseGeometry([1, 2, 3], [null, 4, 5], box).points.split(" ")).toHaveLength(2);
    const none = phaseGeometry([1, 2], [null, null], box);
    expect(none.points).toBe("");
    expect(none.start).toBeNull();
  });
});

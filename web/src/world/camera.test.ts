import { describe, expect, it } from "vitest";

import {
  MAX_ZOOM,
  clamp,
  panBy,
  pixelsPerUnit,
  screenToWorld,
  wholeWorld,
  worldToScreen,
  zoomAt,
} from "./camera";

const world = { width: 200, height: 200 };
const view = { width: 600, height: 600 };

describe("the camera", () => {
  it("shows the whole world at zoom 1, origin bottom-left, y up", () => {
    const cam = wholeWorld(world);
    expect(pixelsPerUnit(cam, world, view)).toBe(3);
    expect(worldToScreen({ x: 0, y: 0 }, cam, world, view)).toEqual({ x: 0, y: 600 });
    expect(worldToScreen({ x: 200, y: 200 }, cam, world, view)).toEqual({ x: 600, y: 0 });
  });

  it("converts screen to world and back exactly", () => {
    const cam = { centre: { x: 70, y: 130 }, zoom: 4 };
    for (const p of [{ x: 0, y: 0 }, { x: 123, y: 456 }, { x: 600, y: 600 }]) {
      const back = worldToScreen(screenToWorld(p, cam, world, view), cam, world, view);
      expect(back.x).toBeCloseTo(p.x, 9);
      expect(back.y).toBeCloseTo(p.y, 9);
    }
  });

  it("zooms about the cursor: the point under it stays under it", () => {
    const cam = wholeWorld(world);
    const cursor = { x: 450, y: 150 };
    const before = screenToWorld(cursor, cam, world, view);
    const zoomed = zoomAt(cam, 3, cursor, world, view);
    const after = screenToWorld(cursor, zoomed, world, view);
    expect(zoomed.zoom).toBe(3);
    expect(after.x).toBeCloseTo(before.x, 9);
    expect(after.y).toBeCloseTo(before.y, 9);
  });

  it("never shows anything outside the world, and keeps zoom in bounds", () => {
    expect(clamp({ centre: { x: -50, y: 999 }, zoom: 1 }, world, view).centre).toEqual({ x: 100, y: 100 });
    const corner = clamp({ centre: { x: 0, y: 0 }, zoom: 4 }, world, view);
    expect(corner.centre).toEqual({ x: 25, y: 25 }); // the view's edge on the world's edge
    expect(clamp({ centre: { x: 100, y: 100 }, zoom: 99 }, world, view).zoom).toBe(MAX_ZOOM);
    expect(zoomAt(wholeWorld(world), 0.1, { x: 0, y: 0 }, world, view).zoom).toBe(1);
  });

  it("pans so the world follows the pointer", () => {
    const cam = { centre: { x: 100, y: 100 }, zoom: 4 };
    const moved = panBy(cam, 120, -60, world, view); // drag right and up by screen pixels
    expect(moved.centre.x).toBeCloseTo(90, 9); // 120 px / 12 px per unit
    expect(moved.centre.y).toBeCloseTo(95, 9);
  });
});

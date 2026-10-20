import { describe, expect, it } from "vitest";

import { SPEED_STEPS, availableControls, sliderToSpeed, speedLabel, speedToSlider } from "./controls";

describe("which controls each state offers", () => {
  it.each([
    ["idle", 0, { run: true, pause: false, step: true, reset: true, save: false }],
    ["running", 50, { run: false, pause: true, step: false, reset: true, save: false }],
    ["paused", 50, { run: true, pause: false, step: true, reset: true, save: true }],
    ["completed", 500, { run: false, pause: false, step: false, reset: true, save: true }],
    ["failed", 20, { run: false, pause: false, step: false, reset: true, save: false }],
  ] as const)("%s at tick %i", (state, tick, expected) => {
    expect(availableControls(state, tick)).toEqual(expected);
  });
});

describe("the speed slider", () => {
  it("spans 1 to 1,000 ticks/s logarithmically, then as fast as possible", () => {
    expect(sliderToSpeed(0)).toBe(1);
    expect(sliderToSpeed(SPEED_STEPS - 1)).toBe(1000);
    expect(sliderToSpeed(SPEED_STEPS)).toBeNull();
    expect(sliderToSpeed(Math.round((SPEED_STEPS - 1) / 3))).toBeCloseTo(10, -0.5); // a third: ~10
  });

  it("finds its place for any speed, including the server's default of 30", () => {
    for (const speed of [1, 30, 200, 1000]) {
      expect(Math.abs(sliderToSpeed(speedToSlider(speed))! - speed) / speed).toBeLessThan(0.07);
    }
    expect(speedToSlider(null)).toBe(SPEED_STEPS);
    expect(speedToSlider(50_000)).toBe(SPEED_STEPS - 1);
  });

  it("names speeds in plain words", () => {
    expect(speedLabel(null)).toBe("As fast as possible");
    expect(speedLabel(1000)).toBe("1,000 ticks/s");
  });
});

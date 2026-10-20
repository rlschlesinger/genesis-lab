import { describe, expect, it } from "vitest";

import { toPixels } from "./tokens";

describe("toPixels", () => {
  it("turns rem into pixels at the root font size", () => {
    expect(toPixels("0.8rem", 16)).toBeCloseTo(12.8);
    expect(toPixels(" 10.625rem ", 16)).toBe(170);
    expect(toPixels("1rem", 20)).toBe(20);
  });

  it("keeps pixels as they are", () => {
    expect(toPixels("52px", 16)).toBe(52);
  });

  it("refuses anything that isn't a rem or px length", () => {
    expect(() => toPixels("", 16)).toThrow();
    expect(() => toPixels("12", 16)).toThrow();
    expect(() => toPixels("1.5em", 16)).toThrow();
  });
});

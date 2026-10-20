import { describe, expect, it } from "vitest";

import { shade, signal, turnPhrase } from "./brain";

describe("the brain view's encodings", () => {
  it("shades by sign and size, clamped to [-1, 1]", () => {
    expect(shade(0.5)).toEqual({ colour: "positive", strength: 0.5 });
    expect(shade(-2)).toEqual({ colour: "negative", strength: 1 });
    expect(shade(0)).toEqual({ colour: "positive", strength: 0 });
  });

  it("a connection carries weight x input", () => {
    expect(signal(-2, 0.5)).toBe(-1);
  });

  it("says turns the way a person would", () => {
    expect(turnPhrase(0.471)).toBe("27.0° left");
    expect(turnPhrase(-0.01)).toBe("0.6° right");
    expect(turnPhrase(0.004)).toBe("straight on");
  });
});

import { describe, expect, it } from "vitest";

import { SPECIALIST, dietKind, dietWords } from "./diet";

describe("a diet in words", () => {
  it("names specialists by the same threshold as the server's diet_low and diet_high", () => {
    expect(SPECIALIST).toBe(0.2);
    expect(dietKind(0)).toBe("eats A");
    expect(dietKind(0.199)).toBe("eats A");
    expect(dietKind(0.2)).toBe("both"); // the server counts diet < 0.2, not <=
    expect(dietKind(0.8)).toBe("both");
    expect(dietKind(0.801)).toBe("eats B");
    expect(dietKind(1)).toBe("eats B");
  });

  it("shows the number as the server sends it, so the words never contradict it", () => {
    expect(dietWords(0.199)).toBe("0.199 (eats A)");
    expect(dietWords(0.5)).toBe("0.500 (both)");
  });
});

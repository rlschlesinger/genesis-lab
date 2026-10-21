import { describe, expect, it } from "vitest";

import type { OrganismColumns } from "../api/types";
import { TRAIL_LENGTH, TrailBook } from "./trails";

const at = (ids: number[], x: number): OrganismColumns => ({
  id: ids, x: ids.map(() => x), y: ids.map(() => 0), heading: ids.map(() => 0),
  energy: ids.map(() => 1), fullness: ids.map(() => 0.5), generation: ids.map(() => 0),
  founder: ids,
});

describe("trails", () => {
  it("keeps the last pictures per organism and forgets the dead", () => {
    const book = new TrailBook();
    for (let k = 0; k < TRAIL_LENGTH + 5; k++) book.record(at([1, 2], k));
    const trail = new Map(book.entries()).get(1)!;
    expect(trail).toHaveLength(TRAIL_LENGTH);
    expect(trail[trail.length - 1]!.x).toBe(TRAIL_LENGTH + 4);
    book.record(at([2], 99));
    expect(book.size).toBe(1);
  });
});

describe("trails for two species", () => {
  it("keeps both groups of one picture, forgetting neither", () => {
    const book = new TrailBook();
    book.record(at([1, 2], 0), at([30], 5));
    book.record(at([1, 2], 1), at([30], 6));
    expect(book.size).toBe(3);
    book.record(at([1], 2), at([30], 7));
    expect([...book.entries()].map(([id]) => id).sort((a, b) => a - b)).toEqual([1, 30]);
  });
});

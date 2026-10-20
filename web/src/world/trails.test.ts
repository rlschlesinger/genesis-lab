import { describe, expect, it } from "vitest";

import type { OrganismColumns } from "../api/types";
import { TRAIL_LENGTH, TrailBook } from "./trails";

const at = (ids: number[], x: number): OrganismColumns => ({
  id: ids, x: ids.map(() => x), y: ids.map(() => 0), heading: ids.map(() => 0),
  energy: ids.map(() => 1), generation: ids.map(() => 0), founder: ids,
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

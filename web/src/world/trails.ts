// Trails: where each organism has been over the last few pictures, kept per organism.

import type { OrganismColumns } from "../api/types";
import type { Point } from "./camera";

export const TRAIL_LENGTH = 24; // pictures: about 1.6 s of history at 15 per second

export class TrailBook {
  private readonly trails = new Map<number, Point[]>();

  /** Add each organism's position from a new picture; forget organisms no longer alive.
   *  Several groups (prey and predators) count as one picture: IDs are unique across them. */
  record(...groups: OrganismColumns[]): void {
    const alive = new Set<number>();
    for (const organisms of groups) this.add(organisms, alive);
    for (const id of this.trails.keys()) if (!alive.has(id)) this.trails.delete(id);
  }

  private add(organisms: OrganismColumns, alive: Set<number>): void {
    for (let i = 0; i < organisms.id.length; i++) {
      const id = organisms.id[i]!;
      alive.add(id);
      let trail = this.trails.get(id);
      if (!trail) {
        trail = [];
        this.trails.set(id, trail);
      }
      trail.push({ x: organisms.x[i]!, y: organisms.y[i]! });
      if (trail.length > TRAIL_LENGTH) trail.shift();
    }
  }

  clear(): void {
    this.trails.clear();
  }

  entries(): IterableIterator<[number, Point[]]> {
    return this.trails.entries();
  }

  get size(): number {
    return this.trails.size;
  }
}

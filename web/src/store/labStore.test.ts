import { beforeEach, describe, expect, it } from "vitest";

import hello from "../api/__fixtures__/hello.json";
import snapshot from "../api/__fixtures__/snapshot.json";
import type { HelloMessage, Snapshot } from "../api/types";
import { initialLabState, useLabStore } from "./labStore";

const snap = (changes: Partial<Snapshot>) => ({ ...(snapshot as Snapshot), ...changes });

beforeEach(() => useLabStore.setState(initialLabState));

describe("the lab store", () => {
  it("shows snapshots of the watched run only", () => {
    useLabStore.getState().watchRun("fixture-run");
    useLabStore.getState().receiveSnapshot(snap({ run_id: "someone-else", tick: 99 }));
    expect(useLabStore.getState().snapshot).toBeNull();
    useLabStore.getState().receiveSnapshot(snap({ tick: 10 }));
    expect(useLabStore.getState().snapshot?.tick).toBe(10);
  });

  it("never goes back in time (a repeat after reconnecting)", () => {
    useLabStore.getState().watchRun("fixture-run");
    useLabStore.getState().receiveSnapshot(snap({ tick: 10 }));
    useLabStore.getState().receiveSnapshot(snap({ tick: 8 }));
    expect(useLabStore.getState().snapshot?.tick).toBe(10);
  });

  it("restarts the stream only when the user picks a run, not when a reset is followed", () => {
    const { watchRun, runReplaced } = useLabStore.getState();
    watchRun("a");
    const picked = useLabStore.getState().subscription;
    runReplaced("b");
    expect(useLabStore.getState().runId).toBe("b");
    expect(useLabStore.getState().subscription).toBe(picked);
    watchRun("c");
    expect(useLabStore.getState().subscription).toBe(picked + 1);
  });

  it("keeps the same world object across reconnections to a world of the same size", () => {
    // PlateCanvas re-creates the renderer when the world object changes; a second hello
    // (a reconnection) with the same size must not throw away the plate's zoom and trails.
    const greeting = hello as HelloMessage;
    useLabStore.getState().watchRun(greeting.run.run_id);
    useLabStore.getState().receiveHello(greeting);
    const world = useLabStore.getState().world;
    useLabStore.getState().receiveHello({ ...greeting, world: { ...greeting.world } });
    expect(useLabStore.getState().world).toBe(world);
    useLabStore.getState().receiveHello({ ...greeting, world: { width: 1, height: 1 } });
    expect(useLabStore.getState().world).toEqual({ width: 1, height: 1 });
  });

  it("forgets the old run's picture and selection when the run changes", () => {
    const store = useLabStore.getState();
    store.watchRun("fixture-run");
    store.receiveSnapshot(snap({ tick: 3 }));
    store.selectOrganism(4);
    useLabStore.getState().watchRun("other");
    expect(useLabStore.getState()).toMatchObject({ snapshot: null, selectedOrganism: null });
  });
});

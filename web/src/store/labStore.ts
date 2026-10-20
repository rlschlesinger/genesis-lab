// The lab's shared state (Zustand). Components read slices of it with selectors and change it
// only through these actions, so the rules for what a message does live in one place.
//
// The store holds a *view* of the server's run, never the run itself: snapshots are replaced
// whole, nothing here is ever sent back as simulation state.

import { create } from "zustand";

import type { HelloMessage, RunInfo, Snapshot } from "../api/types";
import type { StreamStatus } from "../stream/connection";
import type { ViewId } from "../data/views";

export interface World {
  width: number;
  height: number;
}

export interface LabState {
  view: ViewId;
  /** Changes only when the user picks a run; the stream restarts on it (useRunStream). */
  subscription: number;
  /** The run being shown; also changes when a reset is followed (runReplaced). */
  runId: string | null;
  run: RunInfo | null;
  world: World | null;
  snapshot: Snapshot | null;
  status: StreamStatus | "idle";
  statusDetail: string | null;
  selectedOrganism: number | null;
  showTrails: boolean;
  /** The run picker is open (in place of the plate). */
  picking: boolean;

  setView(view: ViewId): void;
  watchRun(runId: string | null): void;
  receiveHello(message: HelloMessage): void;
  receiveSnapshot(snapshot: Snapshot): void;
  setStatus(status: StreamStatus, detail?: string): void;
  runReplaced(newRunId: string): void;
  selectOrganism(id: number | null): void;
  setShowTrails(on: boolean): void;
  setPicking(on: boolean): void;
  /** A control's answer (RunInfo): keep the run's details current between hellos. */
  updateRun(info: RunInfo): void;
}

export const initialLabState = {
  view: "world" as ViewId,
  subscription: 0,
  runId: null,
  run: null,
  world: null,
  snapshot: null,
  status: "idle" as const,
  statusDetail: null,
  selectedOrganism: null,
  showTrails: false,
  picking: false,
};

export const useLabStore = create<LabState>()((set, get) => ({
  ...initialLabState,

  setView: (view) => set({ view }),

  watchRun: (runId) =>
    set((s) => ({
      picking: false,
      subscription: s.subscription + 1,
      runId,
      run: null,
      world: null,
      snapshot: null,
      selectedOrganism: null,
      status: runId === null ? "idle" : s.status,
      statusDetail: null,
    })),

  receiveHello: (message) => set({ run: message.run, world: message.world }),

  receiveSnapshot: (snapshot) => {
    // Ignore a late message from a run we've stopped watching, and never go back in time
    // (after a reconnect the first snapshot can repeat the last one seen).
    const { runId, snapshot: current } = get();
    if (snapshot.run_id !== runId) return;
    if (current && current.run_id === snapshot.run_id && snapshot.tick < current.tick) return;
    // A selected organism that has died stays selected: its details remain readable (5.7).
    set({ snapshot });
  },

  setStatus: (status, detail) => set({ status, statusDetail: detail ?? null }),

  runReplaced: (newRunId) =>
    set({ runId: newRunId, run: null, snapshot: null, selectedOrganism: null }),

  selectOrganism: (id) => set({ selectedOrganism: id }),

  setShowTrails: (on) => set({ showTrails: on }),

  setPicking: (on) => set({ picking: on }),

  updateRun: (info) => {
    if (info.run_id === get().runId) set({ run: info });
  },
}));

// Run controls, with their feedback: which action is waiting for the server, and the
// server's reason if it refused. Shown in place under the controls (no toasts).

import { useCallback, useState } from "react";

import { ApiError, api } from "../api/client";
import type { ExportResult, RunInfo } from "../api/types";
import { useLabStore } from "../store/labStore";

export type ActionName = "run" | "pause" | "step" | "speed" | "reset" | "save";

export interface RunActions {
  pending: ActionName | null;
  error: string | null;
  saved: ExportResult | null;
  run(): void;
  pause(): void;
  step(ticks: number): void;
  setSpeed(ticksPerSecond: number | null): void;
  reset(): void;
  save(): void;
}

export function useRunActions(runId: string | null): RunActions {
  const [pending, setPending] = useState<ActionName | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ExportResult | null>(null);

  const perform = useCallback(
    <T,>(name: ActionName, call: (id: string) => Promise<T>, after?: (result: T) => void) => {
      if (runId === null) return;
      setPending(name);
      setError(null);
      if (name !== "save") setSaved(null);
      call(runId)
        .then((result) => {
          if (isRunInfo(result)) useLabStore.getState().updateRun(result);
          after?.(result);
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : String(e)))
        .finally(() => setPending(null));
    },
    [runId],
  );

  return {
    pending,
    error,
    saved,
    run: () => perform("run", api.resume),
    pause: () => perform("pause", api.pause),
    step: (ticks) => perform("step", (id) => api.step(id, ticks)),
    setSpeed: (speed) => perform("speed", (id) => api.setSpeed(id, speed)),
    // The stream follows the reset run to its new ID by itself (a "gone" message).
    reset: () => perform("reset", (id) => api.reset(id)),
    save: () => perform("save", (id) => api.exportRun(id), setSaved),
  };
}

function isRunInfo(value: unknown): value is RunInfo {
  return typeof value === "object" && value !== null && "run_id" in value && "state" in value;
}

// The selected organism's family in the watched live run. Refetched when the selection
// changes, and every couple of seconds while the run moves (new children are born).

import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { Lineage } from "../api/types";
import { useLabStore } from "../store/labStore";

const REFRESH_MS = 2000;

export function useLineage(): { lineage: Lineage | null; error: string | null } {
  const runId = useLabStore((s) => s.runId);
  const selected = useLabStore((s) => s.selectedOrganism);
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLineage(null);
    setError(null);
    if (runId === null || selected === null) return;
    let current = true;
    let lastTick = -1;
    const load = () => {
      const tick = useLabStore.getState().snapshot?.tick ?? 0;
      if (tick === lastTick) return;
      lastTick = tick;
      api.lineage(runId, selected).then(
        (l) => current && setLineage(l),
        (e: unknown) => current && setError(e instanceof ApiError ? e.detail : String(e)),
      );
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [runId, selected]);

  return { lineage, error };
}

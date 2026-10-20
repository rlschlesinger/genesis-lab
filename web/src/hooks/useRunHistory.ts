// The watched run's history for the charts, kept up to date while the Analytics view is open.
// Asks only for points it doesn't have (series.ts); starts over at a coarser size when the
// run outgrows the current one. Polls about once a second, and only when the run has moved.

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import { type Series, apply, nextRequest } from "../analytics/series";
import { useLabStore } from "../store/labStore";

const POLL_MS = 1000;

export function useRunHistory(): { series: Series | null; error: string | null } {
  const runId = useLabStore((s) => s.runId);
  const [series, setSeries] = useState<Series | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<Series | null>(null);

  useEffect(() => {
    current.current = null;
    setSeries(null);
    setError(null);
    if (runId === null) return;
    let stopped = false;
    let busy = false;
    let lastTick = -1;

    const poll = () => {
      const tick = useLabStore.getState().snapshot?.tick ?? 0;
      if (busy || tick === lastTick) return; // nothing new to ask for
      busy = true;
      const request = nextRequest(current.current, tick);
      api
        .history(runId, request.since, request.every)
        .then((response) => {
          if (stopped) return;
          lastTick = tick;
          current.current = apply(current.current, request, response);
          setSeries(current.current);
          setError(null);
        })
        .catch((e: unknown) => !stopped && setError(e instanceof ApiError ? e.detail : String(e)))
        .finally(() => {
          busy = false;
        });
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [runId]);

  return { series, error };
}

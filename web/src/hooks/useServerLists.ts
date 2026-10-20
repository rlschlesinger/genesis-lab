// What the run picker offers: the configs on the server, and the live runs it holds.

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { ConfigSummary, RunInfo } from "../api/types";

export function useServerLists() {
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([api.configs(), api.runs()])
      .then(([c, r]) => {
        setConfigs(c);
        setRuns(r);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.detail : String(e)));
  }, []);

  useEffect(refresh, [refresh]);
  return { configs, runs, error, refresh };
}

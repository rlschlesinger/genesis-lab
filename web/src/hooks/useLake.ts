// What the Compare view reads from the data lake: experiments, their runs, and one run's
// config and time series. Each request is dropped if the choice changes before it answers.

import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { History, LakeExperiment, LakeRun, LakeRunDetail } from "../api/types";

const reason = (e: unknown) => (e instanceof ApiError ? e.detail : String(e));

export function useLakeExperiments() {
  const [experiments, setExperiments] = useState<LakeExperiment[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.lakeExperiments().then(setExperiments, (e: unknown) => setError(reason(e)));
  }, []);
  return { experiments, error };
}

export function useLakeRuns(experimentId: string | null | undefined) {
  const [runs, setRuns] = useState<LakeRun[]>([]);
  useEffect(() => {
    // Empty at once: the previous experiment's runs must never be offered for this one.
    setRuns([]);
    if (experimentId === undefined) return;
    let current = true;
    api.lakeRuns(experimentId).then((r) => current && setRuns(r), () => current && setRuns([]));
    return () => {
      current = false;
    };
  }, [experimentId]);
  return runs;
}

export interface LakeRunData {
  detail: LakeRunDetail | null;
  series: History | null;
  error: string | null;
}

export function useLakeRun(runId: string | null): LakeRunData {
  const [data, setData] = useState<LakeRunData>({ detail: null, series: null, error: null });
  useEffect(() => {
    setData({ detail: null, series: null, error: null });
    if (runId === null) return;
    let current = true;
    Promise.all([api.lakeRun(runId), api.lakeSeries(runId)]).then(
      ([detail, series]) => current && setData({ detail, series, error: null }),
      (e: unknown) => current && setData({ detail: null, series: null, error: reason(e) }),
    );
    return () => {
      current = false;
    };
  }, [runId]);
  return data;
}

// The selected organism's details, kept current while it's selected. Its brain decides anew
// every tick, so this refetches as snapshots arrive, but at most every REFRESH_MS, and a
// reply that arrives after the selection changed is thrown away.

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { OrganismDetail } from "../api/types";
import { useLabStore } from "../store/labStore";

const REFRESH_MS = 400;

export interface DetailState {
  detail: OrganismDetail | null;
  error: string | null;
}

export function useOrganismDetail(): DetailState {
  const runId = useLabStore((s) => s.runId);
  const selected = useLabStore((s) => s.selectedOrganism);
  const tick = useLabStore((s) => s.snapshot?.tick ?? 0);
  const [state, setState] = useState<DetailState>({ detail: null, error: null });
  const lastFetch = useRef(0);
  const request = useRef(0);

  // A new selection: clear at once, fetch immediately.
  useEffect(() => {
    setState({ detail: null, error: null });
    lastFetch.current = 0;
  }, [runId, selected]);

  useEffect(() => {
    if (runId === null || selected === null) return;
    const wait = Math.max(0, lastFetch.current + REFRESH_MS - performance.now());
    const timer = setTimeout(() => {
      lastFetch.current = performance.now();
      const mine = ++request.current;
      api
        .organism(runId, selected)
        .then((detail) => {
          if (mine === request.current) setState({ detail, error: null });
        })
        .catch((e: unknown) => {
          if (mine === request.current) {
            setState((s) => ({ ...s, error: e instanceof ApiError ? e.detail : String(e) }));
          }
        });
    }, wait);
    return () => clearTimeout(timer);
  }, [runId, selected, tick]);

  return state;
}

// The watched run lives in the address (?run=<run_id>), so a refresh, a bookmark or a link
// brings you back to the same run. Read once on load; kept up to date as the run changes
// (picking another, or following a reset). replaceState: switching runs doesn't fill the
// browser's back history.
import { useEffect } from "react";

import { useLabStore } from "../store/labStore";

export function useRunFromUrl(): void {
  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run");
    if (runId) useLabStore.getState().watchRun(runId);
    return useLabStore.subscribe((next, prev) => {
      if (next.runId === prev.runId) return;
      const url = new URL(window.location.href);
      if (next.runId === null) url.searchParams.delete("run");
      else url.searchParams.set("run", next.runId);
      window.history.replaceState(null, "", url);
    });
  }, []);
}

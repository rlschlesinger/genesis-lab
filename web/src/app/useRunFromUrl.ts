// Until the run picker arrives (5.7), a run can be watched by its ID in the address:
// http://127.0.0.1:5173/?run=<run_id>. Read once, on load.
import { useEffect } from "react";

import { useLabStore } from "../store/labStore";

export function useRunFromUrl(): void {
  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run");
    if (runId) useLabStore.getState().watchRun(runId);
  }, []);
}

// HTTP calls to the API. Each function is one route in docs/API.md. Errors become ApiError
// with the server's own reason, so the interface can say exactly what went wrong.

import type {
  ConfigSummary,
  ExportResult,
  Health,
  OrganismDetail,
  RunCreate,
  RunInfo,
  SavedRun,
} from "./types";

export class ApiError extends Error {
  override name = "ApiError";
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

/** Reached when nothing answers: the API server isn't running. */
export const OFFLINE_STATUS = 0;

type Fetch = typeof fetch;

async function request<T>(fetcher: Fetch, method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(`/api${path}`, {
      method,
      headers: body === undefined ? {} : { "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError(OFFLINE_STATUS, "Can't reach the Genesis Lab API. Start it with: uv run genesis serve");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, readDetail(text) ?? `${method} ${path} failed (${response.status})`);
  }
  return JSON.parse(text) as T;
}

function readDetail(text: string): string | null {
  try {
    const detail: unknown = JSON.parse(text).detail;
    if (typeof detail === "string") return detail;
    // FastAPI's own validation errors are a list of {loc, msg}.
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`)
        .join("; ");
    }
  } catch {
    // not JSON: fall through
  }
  return null;
}

export function createClient(fetcher: Fetch = (...args) => fetch(...args)) {
  const call = <T>(method: string, path: string, body?: unknown) =>
    request<T>(fetcher, method, path, body);
  const run = (id: string) => `/runs/${encodeURIComponent(id)}`;
  return {
    health: () => call<Health>("GET", "/health"),
    configs: () => call<ConfigSummary[]>("GET", "/configs"),
    runs: () => call<RunInfo[]>("GET", "/runs"),
    getRun: (id: string) => call<RunInfo>("GET", run(id)),
    createRun: (body: RunCreate) => call<RunInfo>("POST", "/runs", body),
    deleteRun: (id: string) => call<void>("DELETE", run(id)),
    resume: (id: string) => call<RunInfo>("POST", `${run(id)}/resume`),
    pause: (id: string) => call<RunInfo>("POST", `${run(id)}/pause`),
    step: (id: string, ticks = 1) => call<RunInfo>("POST", `${run(id)}/step`, { ticks }),
    setSpeed: (id: string, ticksPerSecond: number | null) =>
      call<RunInfo>("PUT", `${run(id)}/speed`, { ticks_per_second: ticksPerSecond }),
    reset: (id: string, seed?: number) =>
      call<RunInfo>("POST", `${run(id)}/reset`, seed === undefined ? {} : { seed }),
    organism: (id: string, organismId: number) =>
      call<OrganismDetail>("GET", `${run(id)}/organisms/${organismId}`),
    exportRun: (id: string, ingest = true) =>
      call<ExportResult>("POST", `${run(id)}/export?ingest=${ingest}`),
    savedRuns: (experimentId?: string) =>
      call<SavedRun[]>(
        "GET",
        `/saved-runs${experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : ""}`,
      ),
  };
}

export type ApiClient = ReturnType<typeof createClient>;
export const api = createClient();

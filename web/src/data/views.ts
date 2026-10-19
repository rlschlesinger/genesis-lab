// The lab's four views (roadmap 05B). Labels are what the user reads; ids are stable keys.

export type ViewId = "world" | "analytics" | "compare" | "lineage";

export interface ViewEntry {
  id: ViewId;
  label: string;
  /** Shown when the view has nothing to show yet: what to do next. */
  empty: string;
}

export const VIEWS: readonly ViewEntry[] = [
  { id: "world", label: "World", empty: "Start a run to put a culture on the plate." },
  { id: "analytics", label: "Analytics", empty: "Charts appear once a run is under way." },
  { id: "compare", label: "Compare", empty: "Pick two saved runs to set them side by side." },
  { id: "lineage", label: "Lineage", empty: "Select an organism to trace its family." },
];

// The lab's four views (roadmap 05B). Labels are what the user reads; ids are stable keys.

export type ViewId = "world" | "analytics" | "compare" | "lineage";

export interface ViewEntry {
  id: ViewId;
  label: string;
}

export const VIEWS: readonly ViewEntry[] = [
  { id: "world", label: "World" },
  { id: "analytics", label: "Analytics" },
  { id: "compare", label: "Compare" },
  { id: "lineage", label: "Lineage" },
];

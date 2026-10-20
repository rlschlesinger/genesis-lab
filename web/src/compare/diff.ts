// What differs between two runs' configs: the first question when comparing them.

export interface Difference {
  path: string; // dotted, as in experiment specs: "food.regrowth_per_tick"
  a: string;
  b: string;
}

const LARGE = 12; // lists longer than this (brain weights) are summarised, not printed

function show(value: unknown): string {
  if (Array.isArray(value) && value.length > LARGE) return `${value.length} values`;
  if (value === undefined) return "absent";
  if (value === null) return "none";
  return JSON.stringify(value);
}

function flatten(value: unknown, prefix: string, out: Map<string, unknown>): void {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, inner] of Object.entries(value)) flatten(inner, prefix ? `${prefix}.${key}` : key, out);
  } else {
    out.set(prefix, value);
  }
}

/** Every setting whose value differs, in path order. The seed is a setting too. */
export function configDiff(a: Record<string, unknown>, b: Record<string, unknown>): Difference[] {
  const left = new Map<string, unknown>();
  const right = new Map<string, unknown>();
  flatten(a, "", left);
  flatten(b, "", right);
  const paths = [...new Set([...left.keys(), ...right.keys()])].sort();
  return paths
    .filter((path) => JSON.stringify(left.get(path)) !== JSON.stringify(right.get(path)))
    .map((path) => ({
      path,
      a: show(left.get(path)),
      b: show(right.get(path)),
    }))
    .map((d) => (d.a === d.b ? { ...d, a: `${d.a} (differs)`, b: `${d.b} (differs)` } : d));
}

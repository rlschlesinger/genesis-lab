// Two foods (6.9): how a diet is described. The threshold is the server's (SPECIALIST in
// src/genesis/analytics/metrics.py, which defines the history's diet_low and diet_high), so
// the specimen panel's words and the Specialists chart's prose agree with the numbers drawn.

/** Below this a diet "eats A"; above 1 - SPECIALIST, "eats B". */
export const SPECIALIST = 0.2;

export type DietKind = "eats A" | "eats B" | "both";

export function dietKind(diet: number): DietKind {
  return diet < SPECIALIST ? "eats A" : diet > 1 - SPECIALIST ? "eats B" : "both";
}

/** A diet in words beside its number, e.g. "0.123 (eats A)". Three decimals: the server
 *  sends diets rounded to 0.001, and two would show 0.199 as "0.20 (eats A)" against a chart
 *  that says "below 0.2". */
export function dietWords(diet: number): string {
  return `${diet.toFixed(3)} (${dietKind(diet)})`;
}

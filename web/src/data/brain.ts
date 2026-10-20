// How the brain view shows numbers: values in [-1, 1] as a shade of crystal violet (positive)
// or safranin (negative), never colour alone (the values are printed too).

export function shade(value: number): { colour: "positive" | "negative"; strength: number } {
  const v = Math.max(-1, Math.min(1, value));
  return { colour: v >= 0 ? "positive" : "negative", strength: Math.abs(v) };
}

/** What one connection carries into the next unit: weight x the value feeding it. */
export function signal(weight: number, input: number): number {
  return weight * input;
}

/** Readable names for the seven inputs (brain_inputs.py's INPUT_NAMES, in order). */
export const INPUT_LABELS: Record<string, string> = {
  food_seen: "food seen",
  food_ahead: "food ahead",
  food_left: "food left",
  food_closeness: "food close",
  energy: "energy",
  wall_ahead: "wall ahead",
  noise: "noise",
};

export function turnPhrase(radians: number): string {
  const degrees = Math.abs((radians * 180) / Math.PI);
  if (degrees < 0.5) return "straight on";
  return `${degrees.toFixed(1)}° ${radians > 0 ? "left" : "right"}`;
}

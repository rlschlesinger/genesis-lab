// Which run controls make sense in which state (docs/API.md, "Run states"), the speed scale,
// and the words the controls use. The server enforces the same rules; offering only what it
// would accept means a click never earns a refusal.

import type { RunState } from "../api/types";

export interface Available {
  run: boolean;
  pause: boolean;
  step: boolean;
  reset: boolean;
  save: boolean;
}

export function availableControls(state: RunState, tick: number): Available {
  const stoppable = state === "idle" || state === "paused";
  return {
    run: stoppable,
    pause: state === "running",
    step: stoppable,
    reset: true,
    // Exporting replays the run: it needs a fixed moment (not running) that the replay can
    // reach (not failed), and at least one tick.
    save: tick > 0 && (state === "paused" || state === "completed"),
  };
}

// Speed: a slider from 1 to 1,000 ticks per second on a logarithmic scale (each step of the
// slider multiplies the speed, so slow speeds get as much of the slider as fast ones), plus
// "as fast as possible" (null) at the top.
export const SPEED_STEPS = 60;
export const MIN_SPEED = 1;
export const MAX_SPEED = 1000;

export function sliderToSpeed(position: number): number | null {
  if (position >= SPEED_STEPS) return null;
  const fraction = Math.max(0, position) / (SPEED_STEPS - 1);
  return Math.round(MIN_SPEED * (MAX_SPEED / MIN_SPEED) ** fraction);
}

export function speedToSlider(speed: number | null): number {
  if (speed === null) return SPEED_STEPS;
  const clamped = Math.min(MAX_SPEED, Math.max(MIN_SPEED, speed));
  return Math.round((Math.log(clamped / MIN_SPEED) / Math.log(MAX_SPEED / MIN_SPEED)) * (SPEED_STEPS - 1));
}

export function speedLabel(speed: number | null): string {
  return speed === null ? "As fast as possible" : `${speed.toLocaleString("en")} ticks/s`;
}

export const STEP_SIZES = [1, 10, 100] as const;

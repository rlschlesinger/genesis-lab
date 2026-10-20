import { useEffect, useState } from "react";

import {
  SPEED_STEPS,
  STEP_SIZES,
  availableControls,
  sliderToSpeed,
  speedLabel,
  speedToSlider,
} from "../data/controls";
import { useRunActions } from "../hooks/useRunActions";
import { useLabStore } from "../store/labStore";
import styles from "./StageControls.module.css";

/** Run, pause, step, speed, reset, save. Each button shows its own progress; a refusal
 *  appears in words right under the controls. */
export function StageControls() {
  const runId = useLabStore((s) => s.runId);
  const snapshot = useLabStore((s) => s.snapshot);
  const gone = useLabStore((s) => s.status === "gone");
  const actions = useRunActions(runId);
  // The slider moves freely while dragged; the speed is sent when it's let go.
  const [slider, setSlider] = useState(speedToSlider(snapshot?.speed ?? 30));
  const [dragging, setDragging] = useState(false);
  const serverSpeed = snapshot?.speed ?? 30;
  useEffect(() => {
    if (!dragging) setSlider(speedToSlider(serverSpeed));
  }, [serverSpeed, dragging]);

  // A run that no longer exists can't be controlled; GoneNotice offers what can be done.
  if (snapshot === null || gone) return null;
  const can = availableControls(snapshot.state, snapshot.tick);
  const busy = actions.pending !== null;
  const commitSpeed = () => {
    setDragging(false);
    actions.setSpeed(sliderToSpeed(slider));
  };

  return (
    <div className={styles.controls}>
      <div className={styles.row}>
        {can.pause ? (
          <button type="button" className={styles.primary} onClick={actions.pause} disabled={busy}>
            {actions.pending === "pause" ? "Pausing" : "Pause"}
          </button>
        ) : (
          <button
            type="button"
            className={styles.primary}
            onClick={actions.run}
            disabled={busy || !can.run}
          >
            {actions.pending === "run" ? "Starting" : "Run"}
          </button>
        )}
        <span className={styles.group} role="group" aria-label="Step forward">
          <span className={styles.groupLabel}>Step</span>
          {STEP_SIZES.map((n) => (
            <button
              key={n}
              type="button"
              className="num"
              onClick={() => actions.step(n)}
              disabled={busy || !can.step}
              aria-label={`Step ${n} tick${n === 1 ? "" : "s"}`}
            >
              {n}
            </button>
          ))}
        </span>
        <label className={styles.speed}>
          <span className={styles.groupLabel}>Speed</span>
          <input
            type="range"
            min={0}
            max={SPEED_STEPS}
            value={slider}
            onChange={(e) => {
              setDragging(true);
              setSlider(Number(e.target.value));
            }}
            onPointerUp={commitSpeed}
            onKeyUp={commitSpeed}
            aria-valuetext={speedLabel(sliderToSpeed(slider))}
          />
          <span className={`num ${styles.speedValue}`}>{speedLabel(sliderToSpeed(slider))}</span>
        </label>
        <span className={styles.end}>
          <button type="button" onClick={actions.reset} disabled={busy}>
            {actions.pending === "reset" ? "Resetting" : "Reset"}
          </button>
          <button type="button" onClick={actions.save} disabled={busy || !can.save}>
            {actions.pending === "save" ? "Saving" : "Save run"}
          </button>
        </span>
      </div>
      {actions.error && (
        <p className={styles.error} role="alert">
          {actions.error}
        </p>
      )}
      {actions.saved && (
        <p className={styles.saved} role="status">
          Saved {actions.saved.ticks.toLocaleString("en")} ticks to {actions.saved.path}
          {actions.saved.matches_live_run ? ", identical to the live run" : ""}
          {actions.saved.ingested ? ", and added to the data lake" : ""}.
        </p>
      )}
    </div>
  );
}

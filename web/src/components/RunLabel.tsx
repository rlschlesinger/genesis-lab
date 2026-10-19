import { useLabStore } from "../store/labStore";

/** Which run is on the plate: its config and seed (the two things that determine it). */
export function RunLabel() {
  const run = useLabStore((s) => s.run);
  if (!run) return null;
  return (
    <span title={run.run_id}>
      {run.config_name}, seed <span className="num">{run.seed}</span>
    </span>
  );
}

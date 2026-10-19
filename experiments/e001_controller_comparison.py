"""E001: nearest-food seeker vs random walk, paired seeds. Definition: docs/experiments/E001-*.md

Run:  uv run python experiments/e001_controller_comparison.py

Each run is recorded with execute_run under data/experiments/E001/, then analysed from its
CSV files, so the analysis uses exactly what was recorded (not in-memory state).
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config

EXPERIMENT_ID = "E001"
ROOT = Path(__file__).parents[1]
OUT = ROOT / "data" / "experiments" / EXPERIMENT_ID
CONTROL, TREATMENT = "random_walk", "nearest_food_seeker"
SEEDS = range(10)
SETTLED = slice(2000, 5000)  # ticks 2000-4999

METRICS = ["capacity", "t90", "standing_food", "lifespan", "lineages_end"]


def config_for(controller: str, seed: int) -> SimulationConfig:
    raw = load_config(ROOT / "configs" / "default.yaml").model_dump()
    raw["organisms"]["controller"] = controller
    raw["run"]["seed"] = seed
    return SimulationConfig.model_validate(raw)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def measure(run_dir: Path) -> dict:
    """Compute the pre-registered metrics for one run from its recorded files."""
    ticks = read_csv(run_dir / "ticks.csv")
    organisms = read_csv(run_dir / "organisms.csv")
    meta = json.loads((run_dir / "run.json").read_text())
    pop = [int(t["population"]) for t in ticks]
    food = [int(t["food_count"]) for t in ticks]
    settled = pop[SETTLED]
    if len(settled) < SETTLED.stop - SETTLED.start:  # went extinct before the settled period
        return {"run_id": meta["run_id"], "stop_reason": meta["stop_reason"]} | dict.fromkeys(
            METRICS
        )
    capacity = statistics.fmean(settled)
    t90 = next(i for i, p in enumerate(pop) if p >= 0.9 * capacity)
    ages_at_death = [int(o["age"]) for o in organisms if o["alive"] == "False"]
    return {
        "run_id": meta["run_id"],
        "stop_reason": meta["stop_reason"],
        "capacity": capacity,
        "t90": t90,
        "standing_food": statistics.fmean(food[SETTLED]),
        "lifespan": statistics.median(ages_at_death),
        "lineages_end": int(ticks[-1]["lineages"]),
    }


def main() -> None:
    results: dict[str, dict[int, dict]] = {CONTROL: {}, TREATMENT: {}}
    for controller in (CONTROL, TREATMENT):
        for seed in SEEDS:
            run_dir = OUT / f"{controller}-s{seed}"
            execute_run(
                config_for(controller, seed), run_dir, experiment_id=EXPERIMENT_ID, overwrite=True
            )
            results[controller][seed] = measure(run_dir)
            print(f"  {controller:<20} seed {seed}: {results[controller][seed]['stop_reason']}")

    print("\nPer-seed values (random walk | seeker):")
    print(f"{'seed':>4}  " + "  ".join(f"{m:>23}" for m in METRICS))
    for seed in SEEDS:
        c, t = results[CONTROL][seed], results[TREATMENT][seed]
        print(f"{seed:>4}  " + "  ".join(f"{_fmt(c[m]):>10} | {_fmt(t[m]):<10}" for m in METRICS))

    print("\nPaired differences (seeker - random walk), across seeds:")
    print(f"{'metric':>14}  {'median':>9}  {'min':>9}  {'max':>9}  seeker higher")
    for m in METRICS:
        diffs = paired_differences(results, m)
        higher = sum(d > 0 for d in diffs)
        print(
            f"{m:>14}  {statistics.median(diffs):>9.1f}  {min(diffs):>9.1f}  {max(diffs):>9.1f}"
            f"  {higher}/{len(diffs)}"
        )

    for m in ["capacity"]:
        rel = [
            (results[TREATMENT][s][m] - results[CONTROL][s][m]) / results[CONTROL][s][m]
            for s in SEEDS
            if results[CONTROL][s][m]
        ]
        print(
            f"\ncapacity relative difference: median {statistics.median(rel):+.1%}, "
            f"range {min(rel):+.1%} to {max(rel):+.1%}"
        )

    (OUT / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nper-run metrics saved to {OUT / 'summary.json'}")


def paired_differences(results: dict, metric: str) -> list[float]:
    """Seeker minus random walk, per seed. Seeds where either run went extinct are skipped."""
    diffs = []
    for seed in SEEDS:
        treated, control = results[TREATMENT][seed][metric], results[CONTROL][seed][metric]
        if treated is not None and control is not None:
            diffs.append(treated - control)
    return diffs


def _fmt(value) -> str:
    return "extinct" if value is None else f"{value:.1f}"


if __name__ == "__main__":
    main()

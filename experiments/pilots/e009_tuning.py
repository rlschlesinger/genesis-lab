"""E009 tuning pilots: a meal value V at which populations survive in all three conditions.

    uv run python experiments/pilots/e009_tuning.py

**Tuning, not results.** These runs choose E009's food energy (V, ``food.energy_value``)
before E009 is defined. They report only whether populations survive and how large they
are; they never compute or print anything about the diet, which is what E009 measures.
Seeds 90100 and up, which no experiment uses. Recorded in docs/experiments/pilots/E009-tuning.md.

The three conditions, as the 06B proposal: ``tradeoff`` (configs/diets.yaml: k = 2),
``neutral`` (the diet gene has no effect: everyone digests as a 0.5 generalist) and
``linear`` (k = 1).
"""

from __future__ import annotations

import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from genesis.analytics.experiments import apply_changes
from genesis.core.config import load_config
from genesis.core.simulation import Simulation

ROOT = Path(__file__).resolve().parents[2]
FIRST_SEED, SEEDS, TICKS = 90100, 6, 20000
VALUES = [60.0, 80.0, 100.0]
CONDITIONS = {
    "tradeoff": {},
    "neutral": {"resources.diet.neutral": True},
    "linear": {"resources.exponent": 1.0},
}


def pilot(job: tuple[str, float, int]) -> tuple[str, float, int, int | None, int]:
    """(condition, V, seed, tick the population died out or None, final population)."""
    condition, value, seed = job
    changes = {**CONDITIONS[condition], "food.energy_value": value, "run.seed": seed,
               "run.max_ticks": TICKS}  # fmt: skip
    sim = Simulation(apply_changes(load_config(ROOT / "configs" / "diets.yaml"), changes))
    sim.run()
    gone = sim.tick if not sim.organisms else None
    return condition, value, seed, gone, len(sim.organisms)


def main() -> int:
    jobs = [(c, v, FIRST_SEED + k) for v in VALUES for c in CONDITIONS for k in range(SEEDS)]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(pilot, jobs))
    print(f"{TICKS} ticks, seeds {FIRST_SEED}-{FIRST_SEED + SEEDS - 1} (survival only)\n")
    print(
        f"{'V':>5}  {'condition':<10}{'survived':>9}  {'died out on ticks':<22}{'final population'}"
    )
    for value in VALUES:
        for condition in CONDITIONS:
            runs = [r for r in results if r[0] == condition and r[1] == value]
            gone = sorted(r[3] for r in runs if r[3] is not None)
            alive = [r[4] for r in runs if r[3] is None]
            sizes = (
                f"{min(alive)}-{max(alive)} (median {statistics.median(alive):.0f})"
                if alive
                else "-"
            )
            print(f"{value:>5g}  {condition:<10}{len(alive):>6}/{len(runs)}  "
                  f"{', '.join(map(str, gone)) or '-':<22}{sizes}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

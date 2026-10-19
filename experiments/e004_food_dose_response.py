"""E004 (Experiment A): is the settled population proportional to food? Pre-registered in
docs/experiments/E004-food-dose-response.md; this script implements exactly that analysis.

    uv run python experiments/e004_food_dose_response.py [--smoke | --analyse-only]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from genesis.analytics.analysis import bootstrap_ci, describe_by, query_df
from genesis.analytics.experiment_script import experiment_main
from genesis.analytics.spec import ExperimentSpec

BOUNDS = (0.9, 1.1)  # proportional within +/-10% (the smallest effect of interest)


def settled_populations(spec: ExperimentSpec, lake: Path, window: tuple[int, int]) -> pd.DataFrame:
    """One row per run: food level, settled population, measured living cost per tick."""
    return query_df(
        """
        WITH pop AS (
            SELECT run_id, avg(population) AS settled, count(*) AS rows
            FROM ticks WHERE tick BETWEEN $first AND $last GROUP BY run_id
        ),
        cost AS (
            SELECT run_id, sum(energy_spent) / sum(age) AS cost_per_tick
            FROM organisms WHERE age > 0 GROUP BY run_id
        )
        SELECT p.run_id, p.condition, p.seed, p.food_regrowth AS regrowth, r.stop_reason,
               pop.settled, pop.rows, cost.cost_per_tick
        FROM run_params AS p
        JOIN completed_runs AS r USING (run_id)
        LEFT JOIN pop USING (run_id)
        LEFT JOIN cost USING (run_id)
        WHERE p.experiment_id = $e
        ORDER BY regrowth, p.seed
        """,
        lake,
        {"e": spec.experiment_id, "first": window[0], "last": window[1]},
    )


def elasticity(df: pd.DataFrame) -> float:
    """Slope of ln(population) on ln(food): 1 means proportional."""
    return float(np.polyfit(np.log(df["regrowth"]), np.log(df["settled"]), 1)[0])


def bootstrap_elasticity(df: pd.DataFrame, rng: np.random.Generator, n: int = 10_000):
    """Resample runs *within* each food level, refit, repeat: a 95% CI for the slope."""
    groups = [g.to_numpy() for _, g in df.groupby("regrowth")[["regrowth", "settled"]]]
    slopes = np.empty(n)
    for i in range(n):
        sample = np.vstack([g[rng.integers(0, len(g), len(g))] for g in groups])
        slopes[i] = np.polyfit(np.log(sample[:, 0]), np.log(sample[:, 1]), 1)[0]
    return np.quantile(slopes, [0.025, 0.975])


def analyse(spec: ExperimentSpec, lake: Path, smoke: bool) -> None:
    window = (300, 599) if smoke else (3000, 4999)
    df = settled_populations(spec, lake, window)
    complete = window[1] - window[0] + 1
    usable = df[(df["stop_reason"] != "extinction") & (df["rows"] == complete)]
    print(f"runs: {len(df)}, usable: {len(usable)} (excluded: {len(df) - len(usable)})")
    for level, part in df.groupby("regrowth"):
        dropped = (part["stop_reason"] == "extinction").sum()
        if dropped > 4 and not smoke:
            print(f"food {level}: {dropped} extinct runs: INCONCLUSIVE by the definition")

    print(f"\nsettled population (mean over ticks {window[0]}-{window[1]}) per food level:")
    print(
        describe_by(usable, "regrowth", "settled")[["n", "mean", "sd", "median", "min", "max"]]
        .round(2)
        .to_string()
    )

    beta = elasticity(usable)
    low, high = bootstrap_elasticity(usable, np.random.default_rng(4004))
    if BOUNDS[0] <= low and high <= BOUNDS[1]:
        verdict = "SUPPORTED (proportional within +/-10%)"
    elif high < 1 or low > 1:
        verdict = "REJECTED (not proportional)"
    else:
        verdict = "INCONCLUSIVE"
    print(f"\nH8a elasticity beta = {beta:.3f}, 95% CI [{low:.3f}, {high:.3f}] -> {verdict}")

    print("\nH8b (descriptive) observed / predicted by H1, predicted = regrowth x 20 / cost:")
    usable = usable.assign(
        ratio=usable["settled"] / (usable["regrowth"] * 20 / usable["cost_per_tick"])
    )
    rng = np.random.default_rng(4005)
    for level, part in usable.groupby("regrowth"):
        ci = bootstrap_ci(part["ratio"].to_numpy(), np.median, rng=rng) if len(part) > 1 else None
        cost = part["cost_per_tick"].median()
        print(
            f"  food {level:>4}: median ratio {ci or part['ratio'].median():}  "
            f"(median cost {cost:.3f} EU/tick, {len(part)} runs)"
        )


if __name__ == "__main__":
    sys.exit(experiment_main("E004.yaml", analyse, smoke_ticks=600))

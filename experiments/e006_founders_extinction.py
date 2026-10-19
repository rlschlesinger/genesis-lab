"""E006 (Experiment C): do smaller founding populations go extinct more often?
Pre-registered in docs/experiments/E006-founders-extinction.md; this script implements it.

    uv run python experiments/e006_founders_extinction.py [--smoke | --analyse-only]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from genesis.analytics.analysis import Interval, practical_significance, query_df, wilson_interval
from genesis.analytics.experiment_script import experiment_main
from genesis.analytics.spec import ExperimentSpec

SESOI = 0.15  # difference in extinction probability between 2 and 40 founders


def outcomes(spec: ExperimentSpec, lake: Path) -> pd.DataFrame:
    """One row per completed run: founders, extinct (0/1), and the tick it ended."""
    return query_df(
        """
        SELECT p.run_id, p.seed, p.initial_count AS founders,
               (r.stop_reason = 'extinction')::INTEGER AS extinct,
               r.ticks_run - 1 AS last_tick
        FROM run_params AS p JOIN completed_runs AS r USING (run_id)
        WHERE p.experiment_id = $e
        ORDER BY founders, p.seed
        """,
        lake,
        {"e": spec.experiment_id},
    )


def trend_test(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n: int = 20_000):
    """Correlation of log2(founders) with extinction; two-sided p from shuffling founders.

    A permutation version of the Cochran-Armitage trend test: if founders didn't matter, any
    assignment of the founder labels to the runs' outcomes would be equally likely.
    """
    x = np.log2(x)
    r = float(np.corrcoef(x, y)[0, 1])
    shuffled = np.array([np.corrcoef(rng.permutation(x), y)[0, 1] for _ in range(n)])
    p = (np.sum(np.abs(shuffled) >= abs(r) - 1e-12) + 1) / (n + 1)
    return r, float(p)


def analyse(spec: ExperimentSpec, lake: Path, smoke: bool) -> None:
    df = outcomes(spec, lake)
    print(f"runs: {len(df)}\n\nextinction per founder count (95% Wilson interval):")
    for founders, part in df.groupby("founders"):
        k, n = int(part["extinct"].sum()), len(part)
        print(f"  {founders:>3} founders: {k:>3}/{n:<3} = {wilson_interval(k, n)}")

    if df["extinct"].nunique() < 2:
        print("\nevery run had the same outcome: the trend test is undefined")
        return
    r, p = trend_test(
        df["founders"].to_numpy(),
        df["extinct"].to_numpy(),
        np.random.default_rng(6006),
        n=2_000 if smoke else 20_000,
    )
    verdict = "SUPPORTED" if p < 0.05 and r < 0 else "NOT SUPPORTED"
    print(
        f"\nH10 correlation(log2 founders, extinct) = {r:.3f}, permutation p = {p:.5f} -> {verdict}"
    )

    smallest, largest = df["founders"].min(), df["founders"].max()
    a = df.loc[df["founders"] == smallest, "extinct"].to_numpy()
    b = df.loc[df["founders"] == largest, "extinct"].to_numpy()
    rng = np.random.default_rng(6007)
    diffs = np.array(
        [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(10_000)]
    )
    ci = Interval(float(a.mean() - b.mean()), *np.quantile(diffs, [0.025, 0.975]), 0.95)
    print(
        f"practical: P(extinct | {smallest}) - P(extinct | {largest}) = {ci} -> "
        f"{practical_significance(ci, SESOI)} (SESOI {SESOI})"
    )

    print("\nexploratory: median tick of extinction among extinct runs")
    extinct = df[df["extinct"] == 1]
    print(
        extinct.groupby("founders")["last_tick"].agg(["count", "median", "min", "max"]).to_string()
    )


if __name__ == "__main__":
    sys.exit(experiment_main("E006.yaml", analyse, smoke_ticks=300))

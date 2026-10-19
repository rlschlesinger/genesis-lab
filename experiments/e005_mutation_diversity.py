"""E005 (Experiment B): does a higher mutation rate maintain more neutral diversity?
Pre-registered in docs/experiments/E005-mutation-diversity.md; this script implements it.

    uv run python experiments/e005_mutation_diversity.py [--smoke | --analyse-only]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from genesis.analytics.analysis import Interval, practical_significance, query_df
from genesis.analytics.experiment_script import experiment_main
from genesis.analytics.spec import ExperimentSpec

SESOI = 0.02  # difference in median marker sd between rates 0.02 and 0.3


def settled_sd(spec: ExperimentSpec, lake: Path, window: tuple[int, int]) -> pd.DataFrame:
    """One row per run and gene: the mean of the population sd over the window."""
    return query_df(
        """
        SELECT p.run_id, p.condition, p.seed, p.mutation_rate AS rate, g.gene,
               avg(g.sd) AS settled_sd, count(*) AS rows, count(g.sd) AS rows_with_population
        FROM gene_stats AS g
        JOIN run_params AS p USING (run_id)
        JOIN completed_runs USING (run_id)
        WHERE p.experiment_id = $e AND g.tick BETWEEN $first AND $last
        GROUP BY ALL
        ORDER BY rate, p.seed, g.gene
        """,
        lake,
        {"e": spec.experiment_id, "first": window[0], "last": window[1]},
    )


def permutation_spearman(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n=20_000):
    """Spearman's rho, and a two-sided p from shuffling x (the rate labels)."""
    rho = stats.spearmanr(x, y).statistic
    shuffled = np.array([stats.spearmanr(rng.permutation(x), y).statistic for _ in range(n)])
    p = (np.sum(np.abs(shuffled) >= abs(rho) - 1e-12) + 1) / (n + 1)
    return float(rho), float(p)


def analyse(spec: ExperimentSpec, lake: Path, smoke: bool) -> None:
    window = (500, 599) if smoke else (19_000, 19_999)
    df = settled_sd(spec, lake, window)
    df = df[df["rows_with_population"] == df["rows"]]  # whole window populated
    marker = df[df["gene"] == "neutral_marker"]
    print(f"runs measured: {marker['run_id'].nunique()}")

    zero = marker[marker["rate"] == 0]
    print(
        f"\nC5 rate 0: marker sd exactly 0 in {(zero['settled_sd'] == 0).sum()}/{len(zero)} runs "
        f"-> {'PASS' if (zero['settled_sd'] == 0).all() else 'FAIL'}"
    )

    print("\nmarker sd (mean over the window) per rate:")
    print(
        marker.groupby("rate")["settled_sd"]
        .describe()[["count", "50%", "min", "max"]]
        .rename(columns={"50%": "median"})
        .round(4)
        .to_string()
    )

    test = marker[marker["rate"] > 0]
    rho, p = permutation_spearman(
        test["rate"].to_numpy(),
        test["settled_sd"].to_numpy(),
        np.random.default_rng(5005),
        n=2_000 if smoke else 20_000,
    )
    medians = test.groupby("rate")["settled_sd"].median().to_numpy()
    increasing = bool(np.all(np.diff(medians) > 0))
    ok = p < 0.05 and rho > 0 and increasing
    print(
        f"\nH9 Spearman rho = {rho:.3f}, permutation p = {p:.5f}, medians increasing: {increasing}"
        f" -> {'SUPPORTED' if ok else 'NOT SUPPORTED'}"
    )

    low_rate, high_rate = test["rate"].min(), test["rate"].max()
    a = test.loc[test["rate"] == high_rate, "settled_sd"].to_numpy()
    b = test.loc[test["rate"] == low_rate, "settled_sd"].to_numpy()
    rng = np.random.default_rng(5006)
    diffs = np.array(
        [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(10_000)]
    )
    ci = Interval(float(np.median(a) - np.median(b)), *np.quantile(diffs, [0.025, 0.975]), 0.95)
    print(
        f"practical: median sd at rate {high_rate} minus rate {low_rate}: {ci} -> "
        f"{practical_significance(ci, SESOI)} (SESOI {SESOI})"
    )

    print("\nexploratory: median settled sd per rate for every (neutral) gene")
    print(
        df.pivot_table(index="gene", columns="rate", values="settled_sd", aggfunc="median")
        .round(4)
        .to_string()
    )


if __name__ == "__main__":
    sys.exit(experiment_main("E005.yaml", analyse, smoke_ticks=600))

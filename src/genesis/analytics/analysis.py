"""Analysis tools: query the lake into pandas, describe conditions, confidence intervals,
effect sizes and practical significance.

The unit of analysis is always the **run**: every function here takes one value per run (or
per pair of runs). Organisms within a run share one history and are not independent
replicates (docs/experiment-design.md).

pandas 3 notes: text columns arrive as pandas' string dtype; and copy-on-write means a
filtered selection is never a view into the original, so modify with ``df.loc[...]``, never
with chained indexing like ``df[mask]["col"] = ...`` (which silently does nothing).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from genesis.lake.db import connect
from genesis.lake.ingest import DEFAULT_LAKE

# --- Getting data -------------------------------------------------------------------------


def query_df(sql: str, lake: str | Path = DEFAULT_LAKE, params: dict | None = None) -> pd.DataFrame:
    """Run SQL against the lake's views and return a DataFrame (NULL -> NaN/None)."""
    return connect(lake).execute(sql, params or {}).df()


def settled_gene_means_df(
    experiment_id: str, first_tick: int, last_tick: int, lake: str | Path = DEFAULT_LAKE
) -> pd.DataFrame:
    """One row per completed run: condition, seed, and each gene's settled mean as a column.

    Runs whose window isn't fully populated (extinction during it) are left out, as the
    pre-registered experiments specify.
    """
    long = query_df(
        """
        SELECT p.run_id, p.condition, p.seed, s.gene, s.settled_mean
        FROM settled_gene_means($first, $last) AS s
        JOIN run_params AS p USING (run_id)
        JOIN completed_runs USING (run_id)
        WHERE p.experiment_id = $experiment
          AND s.rows_with_population = s.rows_in_window
        """,
        lake,
        {"first": first_tick, "last": last_tick, "experiment": experiment_id},
    )
    # Long -> wide: one column per gene. pivot needs a unique (row, column) pair, which the
    # macro guarantees (one row per run and gene).
    wide = long.pivot(index=["run_id", "condition", "seed"], columns="gene", values="settled_mean")
    return wide.reset_index().rename_axis(columns=None).sort_values(["condition", "seed"])


# --- Describing groups of runs ------------------------------------------------------------


def describe(values: Sequence[float]) -> dict[str, float]:
    """Summary of one condition's per-run values.

    ``sd`` here is the *sample* standard deviation (divides by n - 1): we are estimating how
    much runs vary in general from a sample of runs. (gene_stats uses the population sd,
    dividing by n, because it describes exactly the organisms present.)
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[~np.isnan(v)]
    n = len(v)
    q1, median, q3 = np.quantile(v, [0.25, 0.5, 0.75]) if n else (math.nan,) * 3
    sd = float(v.std(ddof=1)) if n > 1 else math.nan
    return {
        "n": n,
        "mean": float(v.mean()) if n else math.nan,
        "sd": sd,
        "se": sd / math.sqrt(n) if n > 1 else math.nan,  # standard error of the mean
        "median": float(median),
        "q1": float(q1),
        "q3": float(q3),
        "min": float(v.min()) if n else math.nan,
        "max": float(v.max()) if n else math.nan,
    }


def describe_by(df: pd.DataFrame, group: str, value: str) -> pd.DataFrame:
    """``describe`` for each group (e.g. condition), one row per group."""
    rows = {name: describe(part[value]) for name, part in df.groupby(group, sort=True)}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis(group)


# --- Confidence intervals -----------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float
    confidence: float

    def __str__(self) -> str:
        return f"{self.estimate:.4g} [{self.low:.4g}, {self.high:.4g}]"


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float] = np.median,
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    rng: np.random.Generator | None = None,
) -> Interval:
    """Percentile bootstrap confidence interval for ``statistic`` of the runs' values.

    Resample the runs *with replacement* (the same run can be picked twice), recompute the
    statistic, repeat many times; the middle ``confidence`` share of those results is the
    interval. No assumption about the shape of the distribution. With few runs (say < 10)
    it tends to be too narrow; report n alongside it.

    ``rng`` must be seeded for reproducible intervals.
    """
    v = np.asarray(values, dtype=np.float64)
    if len(v) < 2:
        raise ValueError("a bootstrap interval needs at least 2 values")
    if rng is None:
        raise ValueError("pass a seeded rng, e.g. np.random.default_rng(0)")
    picks = rng.integers(0, len(v), size=(n_resamples, len(v)))  # one resample per row
    try:
        # NumPy statistics (mean, median, ...) can process every resample in one call.
        resampled = np.asarray(statistic(v[picks], axis=1), dtype=np.float64)
    except TypeError:
        resampled = np.apply_along_axis(statistic, 1, v[picks])  # any other function
    alpha = (1 - confidence) / 2
    low, high = np.quantile(resampled, [alpha, 1 - alpha])
    return Interval(float(statistic(v)), float(low), float(high), confidence)


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a proportion, e.g. extinctions out of n runs.

    The simple "p +/- z*sqrt(p(1-p)/n)" interval breaks near 0% and 100%: at 0 of 50 it has
    zero width, and near the edges it can extend below 0 or above 1. Wilson's interval stays
    inside [0, 1] and keeps a sensible width there.
    """
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got {successes} of {n}")
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = successes / n
    centre = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z / (1 + z**2 / n) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half), confidence)


# --- Effect sizes and practical significance ----------------------------------------------


@dataclass(frozen=True)
class PairedEffect:
    n: int
    mean_difference: float  # in the measurement's own units
    median_difference: float
    cohens_dz: float  # mean difference / sd of the differences
    relative_to_control: float  # mean difference / mean of the control values
    ci: Interval  # bootstrap CI of the mean difference


def paired_effect(
    treatment: Sequence[float],
    control: Sequence[float],
    rng: np.random.Generator,
    confidence: float = 0.95,
) -> PairedEffect:
    """Effect size for a paired design (the same seeds in both conditions)."""
    t, c = np.asarray(treatment, dtype=np.float64), np.asarray(control, dtype=np.float64)
    if t.shape != c.shape:
        raise ValueError("paired values must have the same length (one pair per seed)")
    d = t - c
    sd = d.std(ddof=1)
    return PairedEffect(
        n=len(d),
        mean_difference=float(d.mean()),
        median_difference=float(np.median(d)),
        cohens_dz=float(d.mean() / sd) if sd > 0 else math.inf * np.sign(d.mean()),
        relative_to_control=float(d.mean() / c.mean()) if c.mean() != 0 else math.nan,
        ci=bootstrap_ci(d, np.mean, confidence, rng=rng),
    )


def practical_significance(ci: Interval, smallest_effect_of_interest: float) -> str:
    """Compare a confidence interval with an effect size that would matter, stated in advance.

    "Statistically significant" only says an effect is probably not zero; it can still be too
    small to care about. With a smallest effect of interest (SESOI) set before looking:

        meaningful     the whole interval is beyond the SESOI (in either direction)
        negligible     the whole interval is inside +/- SESOI
        inconclusive   the interval overlaps the SESOI boundary: more data needed
    """
    bound = abs(smallest_effect_of_interest)
    if ci.low > bound or ci.high < -bound:
        return "meaningful"
    if -bound < ci.low and ci.high < bound:
        return "negligible"
    return "inconclusive"

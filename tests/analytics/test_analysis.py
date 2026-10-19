"""Tests for the analysis tools, with SciPy as an independent reference where it has one."""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from genesis.analytics.analysis import (
    Interval,
    bootstrap_ci,
    describe,
    describe_by,
    paired_effect,
    practical_significance,
    query_df,
    settled_gene_means_df,
    wilson_interval,
)
from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config
from genesis.lake.ingest import ingest_paths

ROOT = Path(__file__).parents[2]


# --- describe -----------------------------------------------------------------------------


def test_describe_known_values():
    d = describe([1.0, 2.0, 3.0, 4.0, math.nan])
    assert d["n"] == 4  # NaN (a run with no value) is left out
    assert d["mean"] == 2.5 and d["median"] == 2.5
    assert d["sd"] == pytest.approx(np.std([1, 2, 3, 4], ddof=1))  # sample sd, n - 1
    assert d["se"] == pytest.approx(d["sd"] / 2)
    assert (d["min"], d["max"]) == (1.0, 4.0)


def test_describe_single_value_has_no_spread():
    d = describe([5.0])
    assert d["n"] == 1 and math.isnan(d["sd"]) and math.isnan(d["se"])


def test_describe_by_groups():
    df = pd.DataFrame({"condition": ["a", "a", "b", "b", "b"], "x": [1, 3, 10, 20, 30]})
    out = describe_by(df, "condition", "x")
    assert list(out.index) == ["a", "b"]
    assert out.loc["a", "mean"] == 2 and out.loc["b", "median"] == 20


# --- Bootstrap ----------------------------------------------------------------------------


def test_bootstrap_is_reproducible_with_a_seed():
    values = np.random.default_rng(0).normal(10, 2, 20)
    a = bootstrap_ci(values, rng=np.random.default_rng(1))
    b = bootstrap_ci(values, rng=np.random.default_rng(1))
    assert a == b and a.low < a.estimate < a.high


def test_bootstrap_requires_a_seed_and_two_values():
    with pytest.raises(ValueError, match="seeded"):
        bootstrap_ci([1.0, 2.0])
    with pytest.raises(ValueError, match="at least 2"):
        bootstrap_ci([1.0], rng=np.random.default_rng(0))


def test_bootstrap_agrees_with_scipy():
    values = np.random.default_rng(3).normal(5, 1, 25)
    ours = bootstrap_ci(values, np.mean, rng=np.random.default_rng(4), n_resamples=20_000)
    ref = stats.bootstrap(
        (values,), np.mean, method="percentile", n_resamples=20_000, rng=np.random.default_rng(5)
    ).confidence_interval
    assert ours.low == pytest.approx(ref.low, abs=0.03)
    assert ours.high == pytest.approx(ref.high, abs=0.03)


def test_bootstrap_interval_covers_the_true_mean_about_95_percent_of_the_time():
    # Coverage: draw 400 datasets of 30 runs whose true mean is 0. A 95% interval should
    # contain 0 in about 95% of them (the percentile bootstrap runs slightly low at n = 30).
    rng = np.random.default_rng(42)
    hits = sum(
        (ci := bootstrap_ci(rng.normal(0, 1, 30), np.mean, n_resamples=2000, rng=rng)).low
        <= 0
        <= ci.high
        for _ in range(400)
    )
    assert 0.90 <= hits / 400 <= 0.98


def test_bootstrap_accepts_any_statistic():
    values = np.arange(10.0)
    ci = bootstrap_ci(
        values,
        lambda v: float(np.max(v) - np.min(v)),
        rng=np.random.default_rng(0),
        n_resamples=500,
    )
    assert ci.estimate == 9.0 and ci.high <= 9.0


# --- Wilson interval ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("k", "n"), [(0, 50), (1, 50), (7, 50), (25, 50), (49, 50), (50, 50), (3, 10), (0, 1)]
)
def test_wilson_matches_scipy(k, n):
    ours = wilson_interval(k, n)
    ref = stats.binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    assert ours.low == pytest.approx(ref.low, abs=1e-12)
    assert ours.high == pytest.approx(ref.high, abs=1e-12)


def test_wilson_stays_sensible_at_the_edges():
    none = wilson_interval(0, 50)
    assert none.estimate == 0 and none.low == 0 and none.high > 0.05  # not zero width
    simple_high = 0 + 1.96 * math.sqrt(0 * 1 / 50)  # the textbook interval: [0, 0]
    assert simple_high == 0


def test_wilson_rejects_impossible_counts():
    with pytest.raises(ValueError):
        wilson_interval(6, 5)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


# --- Effect sizes -------------------------------------------------------------------------


def test_paired_effect_known_values():
    effect = paired_effect([3.0, 4.0, 5.0], [1.0, 1.0, 1.0], rng=np.random.default_rng(0))
    assert effect.mean_difference == 3 and effect.median_difference == 3
    assert effect.cohens_dz == pytest.approx(3.0)  # mean 3 / sd 1
    assert effect.relative_to_control == pytest.approx(3.0)  # +300% of the control
    assert effect.ci.low <= 3 <= effect.ci.high


def test_paired_effect_needs_equal_lengths():
    with pytest.raises(ValueError, match="same length"):
        paired_effect([1.0, 2.0], [1.0], rng=np.random.default_rng(0))


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (0.6, 0.9, "meaningful"),
        (-0.9, -0.6, "meaningful"),
        (-0.2, 0.3, "negligible"),
        (0.2, 0.8, "inconclusive"),
        (-0.8, 0.8, "inconclusive"),
    ],
)
def test_practical_significance(low, high, expected):
    assert practical_significance(Interval(0.0, low, high, 0.95), 0.5) == expected


def test_significant_but_negligible_is_possible():
    # Many tiny, consistent differences: clearly not zero, yet too small to matter.
    rng = np.random.default_rng(0)
    d = rng.normal(0.02, 0.01, 200)
    assert stats.ttest_1samp(d, 0).pvalue < 1e-6
    ci = bootstrap_ci(d, np.mean, rng=rng)
    assert practical_significance(ci, smallest_effect_of_interest=0.1) == "negligible"


# --- From the lake ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lake(tmp_path_factory) -> Path:
    raw = load_config(ROOT / "configs" / "evolution.yaml").model_dump()
    raw["run"]["max_ticks"] = 200
    runs = tmp_path_factory.mktemp("runs")
    for condition, regrowth in (("plenty", 2.0), ("starve", 0.0)):
        for seed in (1, 2):
            raw["run"]["seed"] = seed
            raw["food"].update(regrowth_per_tick=regrowth, initial_count=150 if regrowth else 0)
            execute_run(
                SimulationConfig.model_validate(raw),
                runs / f"{condition}-s{seed}",
                experiment_id="E900",
                condition=condition,
            )
    lake = tmp_path_factory.mktemp("lake")
    assert all(r.ingested for r in ingest_paths([runs], lake))
    return lake


def test_query_df_returns_a_dataframe_with_pandas_3_strings(lake):
    df = query_df("SELECT run_id, condition, seed FROM completed_runs ORDER BY seed", lake)
    assert len(df) == 4
    assert isinstance(df["condition"].dtype, pd.StringDtype)


def test_settled_means_leave_out_runs_that_died_in_the_window(lake):
    df = settled_gene_means_df("E900", 100, 199, lake)
    starved = query_df("SELECT run_id FROM completed_runs WHERE condition = 'starve'", lake)
    meta = [json.loads(x) for x in query_df("SELECT config FROM completed_runs", lake)["config"]]
    assert all(m["run"]["max_ticks"] == 200 for m in meta)
    assert set(df["condition"]) == {"plenty"}  # the starving runs went extinct before tick 100
    assert not set(df["run_id"]) & set(starved["run_id"])
    assert {"speed", "neutral_marker"} <= set(df.columns)

"""E009: does a population split into specialists on two foods?
Pre-registered in docs/experiments/E009-specialisation.md; this script implements it.

    uv run python experiments/e009_specialisation.py                # run, then analyse
    uv run python experiments/e009_specialisation.py --analyse-only # analyse saved runs
    uv run python experiments/e009_specialisation.py --smoke        # tiny code check

One phase: experiments/specs/E009.yaml runs configs/diets.yaml on seeds 10000-10019 in three
conditions (tradeoff, neutral, linear). Everything measured is the diet of the organisms
alive at the end of each run, read from the lake (diets joined with organisms).
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from genesis.analytics.analysis import paired_effect, query_df
from genesis.analytics.batch import run_experiment
from genesis.analytics.experiment_script import SMOKE_SEEDS
from genesis.analytics.significance import paired_permutation_test
from genesis.analytics.spec import PROJECT_ROOT, ExperimentSpec, load_spec
from genesis.lake.ingest import DEFAULT_LAKE

SPEC = PROJECT_ROOT / "experiments" / "specs" / "E009.yaml"
MIN_SURVIVORS = 30  # a run counts with at least this many organisms alive at the end
SPECIALIST = 0.2  # diet below 0.2 eats A; above 0.8 eats B
SPLIT_SHARE = 0.10  # a world is split with at least 10% of survivors at each end
CONDITIONS = ["tradeoff", "neutral", "linear"]


def run_metrics(spec: ExperimentSpec, lake) -> pd.DataFrame:
    """One row per run: survivors, and their diet's spread, specialisation, split and
    realised diet. ``world`` = the seed's index, pairing a world's three runs."""
    df = query_df(
        f"""
        WITH s AS (
            SELECT d.run_id, d.diet, d.meals_a, d.meals_b
            FROM diets AS d JOIN organisms AS o USING (run_id, organism_id)
            WHERE o.alive)
        SELECT r.condition, r.seed, r.status, r.final_population,
               count(s.diet)                                    AS survivors,
               stddev_pop(s.diet)                               AS diet_sd,
               avg(abs(s.diet - 0.5))                           AS specialisation,
               avg((s.diet < {SPECIALIST})::INTEGER)            AS share_a,
               avg((s.diet > {1 - SPECIALIST})::INTEGER)        AS share_b,
               sum(CASE WHEN s.diet < 0.5 THEN s.meals_a ELSE s.meals_b END)
                 / nullif(sum(s.meals_a + s.meals_b), 0)        AS better_kind
        FROM runs AS r LEFT JOIN s USING (run_id)
        WHERE r.experiment_id = $e AND r.condition IN ('tradeoff', 'neutral', 'linear')
        GROUP BY ALL
        """,
        lake,
        {"e": spec.experiment_id},
    )
    df["world"] = df["seed"] - spec.seed_list()[0]
    df["ok"] = (df["status"] == "completed") & (df["survivors"] >= MIN_SURVIVORS)
    df["split"] = (df["share_a"] >= SPLIT_SHARE) & (df["share_b"] >= SPLIT_SHARE)
    return df.sort_values(["condition", "world"]).reset_index(drop=True)


def paired(df: pd.DataFrame, a: str, b: str, column: str) -> tuple[np.ndarray, np.ndarray]:
    """Values of ``column`` in conditions a and b, for worlds where both runs counted."""
    ok = df[df["ok"]]
    wide = ok.pivot(index="world", columns="condition", values=column)[[a, b]].dropna()
    return wide[a].to_numpy(), wide[b].to_numpy()


def one_sided_greater(differences: np.ndarray, seed: int, n_perm: int) -> tuple[float, float]:
    test = paired_permutation_test(differences, rng=np.random.default_rng(seed), n_samples=n_perm)
    p = test.p_value / 2 if test.observed > 0 else 1 - test.p_value / 2
    return test.observed, p


def analyse(spec: ExperimentSpec, lake, smoke: bool) -> pd.DataFrame:
    df = run_metrics(spec, lake)
    print("runs:")
    for condition in CONDITIONS:
        rows = df[df["condition"] == condition]
        print(f"  {condition}: {int(rows['ok'].sum())} of {len(rows)} counted")
        for row in rows[~rows["ok"]].itertuples():
            print(f"    seed {row.seed}: {row.status}, {row.survivors} alive at the end")
    columns = ["survivors", "diet_sd", "specialisation", "share_a", "share_b", "better_kind"]
    summary = df[df["ok"]].groupby("condition")[columns].agg(["mean", "std"])
    print("\n" + summary.reindex(CONDITIONS).round(4).to_string())
    n_perm = 2_000 if smoke else 20_000

    print("\nH19 (primary) tradeoff - neutral, diet spread (sd) at the end")
    t, n = paired(df, "tradeoff", "neutral", "diet_sd")
    effect = paired_effect(t, n, np.random.default_rng(9119))
    observed, p = one_sided_greater(t - n, 9019, n_perm)
    print(
        f"  mean difference {effect.ci} ({effect.relative_to_control:+.0%} of neutral), "
        f"{np.sum(t > n)}/{len(t)} worlds higher, one-sided p = {p:.5f} -> "
        f"{'SUPPORTED' if p < 0.05 and observed > 0 else 'NOT SUPPORTED'}"
    )

    print("\nH20 (counts) worlds split: at least 10% of survivors below 0.2 and 10% above 0.8")
    for condition in CONDITIONS:
        rows = df[(df["condition"] == condition) & df["ok"]]
        print(f"  {condition}: {int(rows['split'].sum())} of {len(rows)}")

    print("\nH21 (estimate) tradeoff - linear, diet spread (sd) at the end")
    t, li = paired(df, "tradeoff", "linear", "diet_sd")
    effect = paired_effect(t, li, np.random.default_rng(9021))
    test = paired_permutation_test(t - li, rng=np.random.default_rng(9121), n_samples=n_perm)
    print(
        f"  mean difference {effect.ci} ({effect.relative_to_control:+.0%} of linear), "
        f"two-sided p = {test.p_value:.5f}"
    )

    print("\nH22 (secondary) tradeoff - neutral, specialisation (mean |diet - 0.5|) at the end")
    t, n = paired(df, "tradeoff", "neutral", "specialisation")
    effect = paired_effect(t, n, np.random.default_rng(9122))
    observed, p = one_sided_greater(t - n, 9022, n_perm)
    print(
        f"  mean difference {effect.ci}, {np.sum(t > n)}/{len(t)} worlds higher, "
        f"one-sided p = {p:.5f} -> {'SUPPORTED' if p < 0.05 and observed > 0 else 'NOT SUPPORTED'}"
    )
    return df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="tiny code check (throwaway seeds)")
    parser.add_argument("--analyse-only", action="store_true", help="don't run; analyse saved runs")
    parser.add_argument("--rerun-stale", action="store_true")
    args = parser.parse_args()

    spec = load_spec(SPEC)
    lake = PROJECT_ROOT / DEFAULT_LAKE
    if args.smoke:
        spec = spec.smoke_copy(SMOKE_SEEDS, max_ticks=3000)
        lake = spec.output_dir() / "lake"
    if not args.analyse_only:
        print(f"E009: {spec.run_count()} runs planned; running what isn't complete ...")
        outcomes = run_experiment(spec, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}\n")
    analyse(spec, lake, args.smoke)
    return 0


if __name__ == "__main__":
    sys.exit(main())

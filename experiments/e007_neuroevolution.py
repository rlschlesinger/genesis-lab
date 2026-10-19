"""E007: do evolved brains forage as well as the hand-written rule?
Pre-registered in docs/experiments/E007-neuroevolution.md; this script implements it.

    uv run python experiments/e007_neuroevolution.py                # train, evaluate, analyse
    uv run python experiments/e007_neuroevolution.py --analyse-only # analyse saved runs
    uv run python experiments/e007_neuroevolution.py --smoke        # tiny code check

Two phases. Training runs neural.yaml on seeds 7000-7023 (experiments/specs/E007-train.yaml).
Evaluation is then built from the training results by ``evaluation_spec``: a fixed rule, so the
evaluation is as pre-registered as the training even though its brains don't exist yet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from genesis.analytics.analysis import paired_effect, practical_significance, query_df
from genesis.analytics.batch import run_experiment
from genesis.analytics.experiment_script import SMOKE_SEEDS
from genesis.analytics.significance import paired_permutation_test
from genesis.analytics.spec import PROJECT_ROOT, ExperimentSpec, load_spec
from genesis.lake.ingest import DEFAULT_LAKE

TRAIN_SPEC = PROJECT_ROOT / "experiments" / "specs" / "E007-train.yaml"
EVAL_OFFSET = 100  # training seed 7000 + i -> evaluation world 7100 + i
SAMPLE = 30  # brains per evaluation world = founders per evaluation run
MIN_SURVIVORS = SAMPLE  # a training run succeeds with at least this many organisms alive
EVAL_TICKS = 1000
SESOI_FRACTION = 0.05  # H12 and H13: 5% of the reference condition's mean meal rate
CONDITIONS = ["random_walk", "seeker", "random_brains", "evolved", "home"]


# --- Phase 2 is built from phase 1 by this rule ---------------------------------------------


def training_outcomes(spec: ExperimentSpec, lake: Path) -> pd.DataFrame:
    """One row per training seed: its run (if any), status and final population."""
    found = query_df(
        """
        SELECT r.seed, r.run_id, r.status, r.final_population, r.ticks_run
        FROM runs AS r
        WHERE r.experiment_id = $e AND r.condition = 'train'
        """,
        lake,
        {"e": spec.experiment_id},
    )
    seeds = pd.DataFrame({"seed": spec.seed_list()})
    df = seeds.merge(found, on="seed", how="left")
    df["succeeded"] = (df["status"] == "completed") & (df["final_population"] >= MIN_SURVIVORS)
    return df


def evolved_sample(lake: Path, run_id: str, eval_seed: int) -> list[list[float]]:
    """30 brains from a training run's survivors: ordered by organism ID, then drawn with
    ``default_rng(eval_seed).choice(n, 30, replace=False)`` (the pre-registered rule)."""
    brains = query_df(
        """
        SELECT b.* EXCLUDE (run_id)
        FROM brains AS b
        JOIN organisms AS o USING (run_id, organism_id)
        WHERE b.run_id = $r AND o.alive
        ORDER BY b.organism_id
        """,
        lake,
        {"r": run_id},
    )
    weights = brains.drop(columns="organism_id").to_numpy(dtype=np.float64)
    picks = np.random.default_rng(eval_seed).choice(len(weights), SAMPLE, replace=False)
    return [weights[k].tolist() for k in picks]


def evaluation_spec(
    train: ExperimentSpec, lake: Path, eval_ticks: int = EVAL_TICKS
) -> ExperimentSpec:
    """The evaluation phase for every successful training run (docs: Design, phase 2)."""
    outcomes = training_outcomes(train, lake)
    ok = outcomes[outcomes["succeeded"]].sort_values("seed")
    if ok.empty:
        raise RuntimeError("no training run succeeded: nothing to evaluate")
    eval_seeds = [int(s) + EVAL_OFFSET for s in ok["seed"]]
    home_seeds = [int(s) for s in ok["seed"]]
    samples = {
        int(seed): evolved_sample(lake, run_id, int(seed) + EVAL_OFFSET)
        for seed, run_id in zip(ok["seed"], ok["run_id"], strict=True)
    }
    weights = "brain.founder_weights"
    data = {
        "experiment_id": train.experiment_id,
        "title": train.title,
        "definition": train.definition,
        "base_config": "configs/neural.yaml",
        "base_changes": {
            "run.max_ticks": eval_ticks,
            "run.stop_on_extinction": False,
            "organisms.max_population": SAMPLE,  # 30 founders and no room: no births
            "mutation.enabled": False,
        },
        "seeds": eval_seeds,
        "conditions": [
            {"label": "random_walk", "changes": {"organisms.controller": "random_walk"}},
            {"label": "seeker", "changes": {"organisms.controller": "nearest_food_seeker"}},
            {"label": "random_brains"},
            {
                "label": "evolved",
                "per_seed": {s + EVAL_OFFSET: {weights: w} for s, w in samples.items()},
            },
            {
                "label": "home",
                "seeds": home_seeds,
                "per_seed": {s: {weights: w} for s, w in samples.items()},
            },
        ],
        "output": train.output or f"data/experiments/{train.experiment_id}",
    }
    spec = ExperimentSpec.model_validate(data)
    spec.configs()  # validate every run's config now, as load_spec does
    return spec


# --- Metrics and analysis -------------------------------------------------------------------


def evaluation_metrics(spec: ExperimentSpec, lake: Path) -> pd.DataFrame:
    """One row per evaluation run, with ``world`` = the training index i that pairs them."""
    df = query_df(
        """
        WITH t AS (SELECT run_id, sum(food_eaten) AS meals FROM ticks GROUP BY run_id),
             b AS (SELECT run_id, sum(n) AS organism_ticks, avg(mean_throttle) AS throttle,
                          sum(toward_food * seeing_food) / nullif(sum(seeing_food), 0) AS toward
                   FROM behaviour GROUP BY run_id),
             o AS (SELECT run_id, sum(energy_spent) AS energy_spent FROM organisms GROUP BY run_id)
        SELECT r.condition, r.seed, r.final_population AS survivors,
               t.meals, b.organism_ticks, t.meals / b.organism_ticks AS meal_rate,
               o.energy_spent / nullif(t.meals, 0) AS energy_per_meal, b.throttle, b.toward
        FROM completed_runs AS r JOIN t USING (run_id) JOIN b USING (run_id) JOIN o USING (run_id)
        WHERE r.experiment_id = $e AND r.condition IN ('random_walk', 'seeker', 'random_brains',
                                                        'evolved', 'home')
        """,
        lake,
        {"e": spec.experiment_id},
    )
    first_train = spec.seed_list()[0]
    df["world"] = np.where(
        df["condition"] == "home", df["seed"] - first_train, df["seed"] - first_train - EVAL_OFFSET
    )
    return df.sort_values(["condition", "world"]).reset_index(drop=True)


def paired(df: pd.DataFrame, a: str, b: str, column: str) -> tuple[np.ndarray, np.ndarray]:
    wide = df.pivot(index="world", columns="condition", values=column)[[a, b]].dropna()
    return wide[a].to_numpy(), wide[b].to_numpy()


def verdict(category: str, estimate: float) -> str:
    if category == "negligible":
        return "EQUIVALENT"
    if category == "meaningful":
        return "BETTER" if estimate > 0 else "WORSE"
    return "INCONCLUSIVE"


def analyse(train: ExperimentSpec, lake: Path, smoke: bool) -> None:
    outcomes = training_outcomes(train, lake)
    failed = outcomes[~outcomes["succeeded"]]
    print(f"training: {int(outcomes['succeeded'].sum())} of {len(outcomes)} runs succeeded")
    for row in failed.itertuples():
        print(f"  seed {row.seed}: {row.status}, final population {row.final_population}")

    df = evaluation_metrics(train, lake)
    print(f"\nevaluation: {df['world'].nunique()} worlds, {len(df)} runs")
    summary = df.groupby("condition")[
        ["meal_rate", "energy_per_meal", "survivors", "throttle", "toward"]
    ].agg(["mean", "std"])
    print(summary.reindex(CONDITIONS).round(4).to_string())
    n_perm = 2_000 if smoke else 20_000

    print("\nH11 (positive control) evolved - random_brains, meals per organism-tick")
    ev, rb = paired(df, "evolved", "random_brains", "meal_rate")
    h11 = paired_permutation_test(ev - rb, rng=np.random.default_rng(7011), n_samples=n_perm)
    one_sided = h11.p_value / 2 if h11.observed > 0 else 1 - h11.p_value / 2
    passed = one_sided < 0.05 and h11.observed > 0
    print(
        f"  mean difference {h11.observed:+.5f}, {np.sum(ev > rb)}/{len(ev)} worlds higher, "
        f"one-sided p = {one_sided:.5f} -> {'SUPPORTED' if passed else 'NOT SUPPORTED'}"
    )
    if not passed:
        print("  H11 failed: per the definition, H12 and H13 are inconclusive")

    for name, a, b, seed in [("H12", "evolved", "seeker", 7012), ("H13", "evolved", "home", 7013)]:
        x, y = paired(df, a, b, "meal_rate")
        effect = paired_effect(x, y, np.random.default_rng(seed))
        sesoi = SESOI_FRACTION * y.mean()
        category = practical_significance(effect.ci, sesoi)
        label = verdict(category, effect.mean_difference) if passed else "INCONCLUSIVE (H11 gate)"
        print(f"\n{name} {a} - {b}, meals per organism-tick (n = {effect.n} worlds)")
        print(
            f"  mean difference {effect.ci} ({effect.relative_to_control:+.1%} of {b}), "
            f"SESOI +/-{sesoi:.5f} -> {label}"
        )

    print("\nH14 (secondary) evolved - seeker, energy spent per meal")
    x, y = paired(df, "evolved", "seeker", "energy_per_meal")
    effect = paired_effect(x, y, np.random.default_rng(7014))
    test = paired_permutation_test(x - y, rng=np.random.default_rng(7015), n_samples=n_perm)
    print(
        f"  mean difference {effect.ci} EU per meal ({effect.relative_to_control:+.1%} of "
        f"seeker), two-sided p = {test.p_value:.5f}"
    )


# --- Command line ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="tiny code check (throwaway seeds)")
    parser.add_argument("--analyse-only", action="store_true", help="don't run; analyse saved runs")
    parser.add_argument("--rerun-stale", action="store_true")
    args = parser.parse_args()

    train = load_spec(TRAIN_SPEC)
    lake, eval_ticks = PROJECT_ROOT / DEFAULT_LAKE, EVAL_TICKS
    if args.smoke:
        train = train.smoke_copy(SMOKE_SEEDS, max_ticks=3000)
        lake, eval_ticks = train.output_dir() / "lake", 200
    if not args.analyse_only:
        print(f"E007 training: {train.run_count()} runs planned; running what isn't complete ...")
        outcomes = run_experiment(train, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}")
        evaluation = evaluation_spec(train, lake, eval_ticks)
        # A readable record of exactly what was evaluated (weights included).
        record = train.output_dir() / "evaluation-spec.yaml"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(yaml.safe_dump(evaluation.model_dump(mode="json"), sort_keys=False))
        print(f"E007 evaluation: {evaluation.run_count()} runs planned (spec: {record}) ...")
        outcomes = run_experiment(evaluation, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}\n")
    analyse(train, lake, args.smoke)
    return 0


if __name__ == "__main__":
    sys.exit(main())

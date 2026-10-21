"""E008: do prey evolve to escape predators?
Pre-registered in docs/experiments/E008-evasion.md; this script implements it.

    uv run python experiments/e008_evasion.py                # train, test, analyse
    uv run python experiments/e008_evasion.py --analyse-only # analyse saved runs
    uv run python experiments/e008_evasion.py --smoke        # tiny code check

Two phases, as E007. Training runs the tuned predator world on seeds 8000-8019 twice: with
predators ("hunted") and with none ("safe"; experiments/specs/E008-train.yaml). The test arena
is then built from the training results by ``arena_spec``: a fixed rule, so the arena is as
pre-registered as the training even though its brains don't exist yet.
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
from genesis.intelligence.brain_inputs import PREY_INPUT_NAMES, parameter_names
from genesis.lake.ingest import DEFAULT_LAKE

TRAIN_SPEC = PROJECT_ROOT / "experiments" / "specs" / "E008-train.yaml"
ARENA_OFFSET = 100  # training seed 8000 + i -> arena world 8100 + i
SAMPLE = 30  # brains per arena run = prey founders per arena run
MIN_SURVIVORS = SAMPLE  # a training run succeeds with at least this many prey alive
ARENA_TICKS = 1000
ARENA_PREDATORS = 4
SESOI_FRACTION = 0.10  # H17: 10% of the designed flee rule's mean capture rate
TRAINING = ["hunted", "safe"]
# Arena groups. Named apart from the training conditions: one experiment's runs share a lake,
# so a label used in both phases would mix training runs into the arena's measurements (the
# smoke run caught exactly that).
CONDITIONS = ["seeker", "flee", "from_safe", "from_hunted"]
# A prey brain's 80 parameters in Brain.to_vector() order. Not the lake's column order: there
# the 18 predator-input weights come after the first 62 (D-060); in a brain's own vector each
# hidden unit's ten weights sit together.
BRAIN_ORDER = parameter_names(PREY_INPUT_NAMES)


# --- Phase 2 is built from phase 1 by this rule ---------------------------------------------


def training_outcomes(spec: ExperimentSpec, lake: Path) -> pd.DataFrame:
    """One row per (training condition, seed): its run (if any), status and prey at the end,
    plus when the predators died out (hunted only; NULL if they lasted the whole run)."""
    found = query_df(
        """
        SELECT r.condition, r.seed, r.run_id, r.status, r.final_population, r.ticks_run,
               r.final_predators,
               (SELECT min(p.tick) FROM predator_ticks AS p
                WHERE p.run_id = r.run_id AND p.population = 0) AS predators_gone
        FROM runs AS r
        WHERE r.experiment_id = $e AND r.condition IN ('hunted', 'safe')
        """,
        lake,
        {"e": spec.experiment_id},
    )
    grid = pd.DataFrame(
        [(c, s) for c in TRAINING for s in spec.seed_list()], columns=["condition", "seed"]
    )
    df = grid.merge(found, on=["condition", "seed"], how="left")
    df["succeeded"] = (df["status"] == "completed") & (df["final_population"] >= MIN_SURVIVORS)
    return df


def evolved_sample(lake: Path, run_id: str, arena_seed: int) -> list[list[float]]:
    """30 brains from a training run's surviving prey: ordered by organism ID, then drawn with
    ``default_rng(arena_seed).choice(n, 30, replace=False)`` (the pre-registered rule)."""
    columns = ", ".join(f"b.{c}" for c in BRAIN_ORDER)
    brains = query_df(
        f"""
        SELECT {columns}
        FROM brains AS b
        JOIN organisms AS o USING (run_id, organism_id)
        WHERE b.run_id = $r AND o.alive
        ORDER BY b.organism_id
        """,
        lake,
        {"r": run_id},
    )
    weights = brains.to_numpy(dtype=np.float64)
    picks = np.random.default_rng(arena_seed).choice(len(weights), SAMPLE, replace=False)
    return [weights[k].tolist() for k in picks]


def arena_base_changes(ticks: int = ARENA_TICKS) -> dict:
    """The test arena: 30 prey and no births, mutation off, and 4 chasers that can neither
    starve nor breed (no living costs, no births), so every group faces the same, constant
    predation for the whole run. Births are switched off, not just capped: a cap only stops
    births while nobody dies, and here captures free room."""
    return {
        "run.max_ticks": ticks,
        "run.stop_on_extinction": False,
        "organisms.initial_count": SAMPLE,
        "organisms.max_population": SAMPLE,
        "organisms.births": False,
        "mutation.enabled": False,
        "predators.initial_count": ARENA_PREDATORS,
        "predators.max_population": ARENA_PREDATORS,
        "predators.births": False,
        "predators.move_cost_per_distance": 0.0,  # no costs: predators can't starve
        "predators.sense_cost_per_unit": 0.0,
        "predators.genome.metabolic_rate.min": 0.0,
        "predators.genome.metabolic_rate.initial": 0.0,
        "recording.ticks_every": 1,
    }


def arena_spec(train: ExperimentSpec, lake: Path, ticks: int = ARENA_TICKS) -> ExperimentSpec:
    """The test arena for every world whose hunted and safe training runs both succeeded."""
    outcomes = training_outcomes(train, lake)
    ok = outcomes.pivot(index="seed", columns="condition", values="succeeded").fillna(False)
    worlds = sorted(int(s) for s in ok.index if ok.loc[s, "hunted"] and ok.loc[s, "safe"])
    if not worlds:
        raise RuntimeError("no world has both training runs succeeding: nothing to test")
    runs = outcomes.set_index(["condition", "seed"])["run_id"]
    weights = "brain.founder_weights"
    samples = {
        label: {
            seed + ARENA_OFFSET: {
                weights: evolved_sample(lake, runs[(label, seed)], seed + ARENA_OFFSET)
            }
            for seed in worlds
        }
        for label in TRAINING
    }
    data = {
        "experiment_id": train.experiment_id,
        "title": train.title,
        "definition": train.definition,
        "base_config": "configs/predators.yaml",
        "base_changes": arena_base_changes(ticks),
        "seeds": [s + ARENA_OFFSET for s in worlds],
        "conditions": [
            {"label": "seeker", "changes": {"organisms.controller": "nearest_food_seeker"}},
            {"label": "flee", "changes": {"organisms.controller": "flee_seeker"}},
            {"label": "from_safe", "per_seed": samples["safe"]},
            {"label": "from_hunted", "per_seed": samples["hunted"]},
        ],
        "output": train.output or f"data/experiments/{train.experiment_id}",
    }
    spec = ExperimentSpec.model_validate(data)
    spec.configs()  # validate every run's config now, as load_spec does
    return spec


# --- Metrics and analysis -------------------------------------------------------------------


def arena_metrics(spec: ExperimentSpec, lake: Path) -> pd.DataFrame:
    """One row per arena run, with ``world`` = the training index i that pairs them."""
    df = query_df(
        """
        WITH t AS (SELECT run_id, sum(food_eaten) AS meals FROM ticks GROUP BY run_id),
             p AS (SELECT run_id, sum(captures) AS captures, sum(attempts) AS strikes
                   FROM predator_ticks GROUP BY run_id),
             b AS (SELECT run_id, sum(n) AS prey_ticks, avg(mean_throttle) AS throttle
                   FROM behaviour GROUP BY run_id)
        SELECT r.condition, r.seed, r.final_population AS survivors, t.meals, p.captures,
               p.strikes, b.prey_ticks, p.captures / b.prey_ticks AS capture_rate,
               t.meals / b.prey_ticks AS meal_rate,
               p.captures / nullif(p.strikes, 0) AS strike_success, b.throttle
        FROM completed_runs AS r JOIN t USING (run_id) JOIN p USING (run_id)
             JOIN b USING (run_id)
        WHERE r.experiment_id = $e
          AND r.condition IN ('seeker', 'flee', 'from_safe', 'from_hunted')
        """,
        lake,
        {"e": spec.experiment_id},
    )
    df["world"] = df["seed"] - spec.seed_list()[0] - ARENA_OFFSET
    return df.sort_values(["condition", "world"]).reset_index(drop=True)


def paired(df: pd.DataFrame, a: str, b: str, column: str) -> tuple[np.ndarray, np.ndarray]:
    wide = df.pivot(index="world", columns="condition", values=column)[[a, b]].dropna()
    return wide[a].to_numpy(), wide[b].to_numpy()


def one_sided_lower(differences: np.ndarray, seed: int, n_perm: int) -> tuple[float, float]:
    """Mean difference and the one-sided p-value for "a is lower than b"."""
    test = paired_permutation_test(differences, rng=np.random.default_rng(seed), n_samples=n_perm)
    p = test.p_value / 2 if test.observed < 0 else 1 - test.p_value / 2
    return test.observed, p


def analyse(train: ExperimentSpec, lake: Path, smoke: bool) -> dict:
    outcomes = training_outcomes(train, lake)
    print("training:")
    for label in TRAINING:
        rows = outcomes[outcomes["condition"] == label]
        print(f"  {label}: {int(rows['succeeded'].sum())} of {len(rows)} runs succeeded")
        for row in rows[~rows["succeeded"]].itertuples():
            print(f"    seed {row.seed}: {row.status}, {row.final_population} prey at the end")
    hunted = outcomes[outcomes["condition"] == "hunted"]
    lasted = hunted["predators_gone"].isna() & (hunted["status"] == "completed")
    print(f"  predators lasted the whole run in {int(lasted.sum())} of {len(hunted)} hunted worlds")
    gone = hunted["predators_gone"].dropna()
    if len(gone):
        print(f"  elsewhere they died out on ticks {', '.join(str(int(t)) for t in sorted(gone))}")

    df = arena_metrics(train, lake)
    print(f"\narena: {df['world'].nunique()} worlds, {len(df)} runs")
    summary = df.groupby("condition")[
        ["capture_rate", "meal_rate", "survivors", "strike_success", "throttle"]
    ].agg(["mean", "std"])
    print(summary.reindex(CONDITIONS).round(5).to_string())
    n_perm = 2_000 if smoke else 20_000

    print("\nH15 (positive control) flee - seeker, captures per prey-tick")
    fl, sk = paired(df, "flee", "seeker", "capture_rate")
    observed, p = one_sided_lower(fl - sk, 8015, n_perm)
    gate = p < 0.05 and observed < 0
    print(
        f"  mean difference {observed:+.6f}, {np.sum(fl < sk)}/{len(fl)} worlds lower, "
        f"one-sided p = {p:.5f} -> {'SUPPORTED' if gate else 'NOT SUPPORTED'}"
    )
    if not gate:
        print("  H15 failed: per the definition, the arena can't show evasion; H16 inconclusive")

    print("\nH16 (primary) from_hunted - from_safe, captures per prey-tick")
    hu, sa = paired(df, "from_hunted", "from_safe", "capture_rate")
    effect = paired_effect(hu, sa, np.random.default_rng(8016))
    observed, p = one_sided_lower(hu - sa, 8116, n_perm)
    supported = p < 0.05 and observed < 0
    label = ("SUPPORTED" if supported else "NOT SUPPORTED") if gate else "INCONCLUSIVE (H15 gate)"
    print(
        f"  mean difference {effect.ci} ({effect.relative_to_control:+.1%} of from_safe), "
        f"{np.sum(hu < sa)}/{len(hu)} worlds lower, one-sided p = {p:.5f} -> {label}"
    )

    print("\nH17 (estimate) from_hunted - flee, captures per prey-tick")
    hu, fl = paired(df, "from_hunted", "flee", "capture_rate")
    effect = paired_effect(hu, fl, np.random.default_rng(8017))
    sesoi = SESOI_FRACTION * fl.mean()
    category = practical_significance(effect.ci, sesoi)
    if category == "negligible":
        verdict = "EQUIVALENT"
    elif category == "meaningful":
        verdict = "EVOLVED CAUGHT LESS" if effect.mean_difference < 0 else "DESIGNED CAUGHT LESS"
    else:
        verdict = "INCONCLUSIVE"
    print(
        f"  mean difference {effect.ci} ({effect.relative_to_control:+.1%} of flee), "
        f"SESOI +/-{sesoi:.6f} -> {verdict}"
    )

    print("\nH18 (secondary) from_hunted - from_safe, meals per prey-tick")
    hu, sa = paired(df, "from_hunted", "from_safe", "meal_rate")
    effect = paired_effect(hu, sa, np.random.default_rng(8018))
    test = paired_permutation_test(hu - sa, rng=np.random.default_rng(8019), n_samples=n_perm)
    print(
        f"  mean difference {effect.ci} ({effect.relative_to_control:+.1%} of from_safe), "
        f"two-sided p = {test.p_value:.5f}"
    )
    return {"metrics": df, "training": outcomes}


# --- Command line ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="tiny code check (throwaway seeds)")
    parser.add_argument("--analyse-only", action="store_true", help="don't run; analyse saved runs")
    parser.add_argument("--rerun-stale", action="store_true")
    args = parser.parse_args()

    train = load_spec(TRAIN_SPEC)
    lake, ticks = PROJECT_ROOT / DEFAULT_LAKE, ARENA_TICKS
    if args.smoke:
        train = train.smoke_copy(SMOKE_SEEDS, max_ticks=3000)
        lake, ticks = train.output_dir() / "lake", 200
    if not args.analyse_only:
        print(f"E008 training: {train.run_count()} runs planned; running what isn't complete ...")
        outcomes = run_experiment(train, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}")
        arena = arena_spec(train, lake, ticks)
        # A readable record of exactly what was tested (weights included).
        record = train.output_dir() / "arena-spec.yaml"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(yaml.safe_dump(arena.model_dump(mode="json"), sort_keys=False))
        print(f"E008 arena: {arena.run_count()} runs planned (spec: {record}) ...")
        outcomes = run_experiment(arena, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}\n")
    analyse(train, lake, args.smoke)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The pre-registered E004-E007 analyses, checked on synthetic data with known answers.

A bug in an analysis is as damaging as a bug in the simulation, so each statistical helper is
tested before any real run is analysed.
"""

import importlib.util

import numpy as np
import pandas as pd
import pytest

from genesis.analytics.spec import PROJECT_ROOT, load_spec

EXPERIMENTS = PROJECT_ROOT / "experiments"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e004 = load("e004_food_dose_response")
e005 = load("e005_mutation_diversity")
e006 = load("e006_founders_extinction")
e007 = load("e007_neuroevolution")


@pytest.mark.parametrize("power", [1.0, 0.5, 1.3])
def test_elasticity_recovers_the_exponent(power):
    food = np.repeat([0.5, 1, 2, 4], 10)
    df = pd.DataFrame({"regrowth": food, "settled": 57.0 * food**power})
    assert e004.elasticity(df) == pytest.approx(power)


def test_elasticity_ci_covers_one_for_noisy_proportional_data():
    rng = np.random.default_rng(0)
    food = np.repeat([0.5, 1, 2, 4], 10)
    df = pd.DataFrame({"regrowth": food, "settled": 57 * food * rng.normal(1, 0.03, 40)})
    low, high = e004.bootstrap_elasticity(df, np.random.default_rng(1), n=2000)
    assert low < 1 < high and high - low < 0.1


def test_spearman_permutation_detects_a_trend_and_not_noise():
    rng = np.random.default_rng(2)
    rates = np.repeat([0.02, 0.1, 0.3], 10)
    rho, p = e005.permutation_spearman(rates, rates + rng.normal(0, 0.05, 30), rng, n=2000)
    assert rho > 0.5 and p < 0.01
    rho, p = e005.permutation_spearman(rates, rng.normal(0, 1, 30), rng, n=2000)
    assert p > 0.05


def test_trend_test_detects_decreasing_extinction():
    founders = np.repeat([2, 5, 10, 20, 40], 50)
    probability = {2: 0.8, 5: 0.6, 10: 0.45, 20: 0.3, 40: 0.15}
    rng = np.random.default_rng(3)
    extinct = np.array([rng.random() < probability[f] for f in founders], dtype=int)
    r, p = e006.trend_test(founders, extinct, rng, n=2000)
    assert r < 0 and p < 0.01


def test_trend_test_finds_nothing_when_founders_dont_matter():
    founders = np.repeat([2, 5, 10, 20, 40], 50)
    rng = np.random.default_rng(4)
    r, p = e006.trend_test(founders, (rng.random(250) < 0.5).astype(int), rng, n=2000)
    assert p > 0.05


@pytest.mark.parametrize(("name", "runs"), [("E004", 40), ("E005", 40), ("E006", 250)])
def test_specs_plan_the_pre_registered_runs(name, runs):
    spec = load_spec(EXPERIMENTS / "specs" / f"{name}.yaml")
    assert len(spec.seed_list()) * len(spec.conditions) == runs
    assert (PROJECT_ROOT / spec.definition).exists()


def test_smoke_copy_is_isolated_from_the_real_experiment():
    spec = load_spec(EXPERIMENTS / "specs" / "E006.yaml")
    smoke = spec.smoke_copy([9100, 9101], 300)
    assert smoke.seed_list() == [9100, 9101]
    assert smoke.base_changes["run.max_ticks"] == 300
    assert smoke.base_changes["food.regrowth_per_tick"] == 0.1  # keeps the experiment's settings
    assert smoke.output_dir() != spec.output_dir()
    assert not set(smoke.seed_list()) & set(spec.seed_list())


# --- E007: the evaluation rule and the verdicts ---------------------------------------------


def test_e007_training_spec_plans_24_runs_on_fresh_seeds():
    spec = load_spec(EXPERIMENTS / "specs" / "E007-train.yaml")
    assert spec.seed_list() == list(range(7000, 7024))
    assert spec.run_count() == 24
    assert (PROJECT_ROOT / spec.definition).exists()
    earlier = ["E001", "E002", "E003", "E004", "E005", "E006"]
    used_before = {
        s for name in earlier for s in load_spec(EXPERIMENTS / "specs" / f"{name}.yaml").seed_list()
    }
    evaluation = {s + e007.EVAL_OFFSET for s in spec.seed_list()}
    assert not (set(spec.seed_list()) | evaluation) & used_before


@pytest.mark.parametrize(
    "category, estimate, expected",
    [
        ("negligible", 0.001, "EQUIVALENT"),
        ("meaningful", 0.01, "BETTER"),
        ("meaningful", -0.01, "WORSE"),
        ("inconclusive", 0.01, "INCONCLUSIVE"),
    ],
)
def test_e007_verdicts_follow_the_definition(category, estimate, expected):
    assert e007.verdict(category, estimate) == expected


@pytest.fixture(scope="module")
def e007_trained(tmp_path_factory):
    """Two short training runs (throwaway seeds) in a private folder and lake."""
    from genesis.analytics.batch import run_experiment

    out = tmp_path_factory.mktemp("e007")
    train = load_spec(EXPERIMENTS / "specs" / "E007-train.yaml").smoke_copy([9100, 9101], 1500)
    train = train.model_copy(update={"output": str(out / "runs")})
    lake = out / "lake"
    run_experiment(train, workers=1, lake=lake)
    return train, lake


def test_e007_evaluation_follows_the_pre_registered_rule(e007_trained):
    train, lake = e007_trained
    evaluation = e007.evaluation_spec(train, lake, eval_ticks=50)
    labels = [c.label for c in evaluation.conditions]
    assert labels == ["random_walk", "seeker", "random_brains", "evolved", "home"]
    assert evaluation.seed_list() == [9200, 9201]  # training seed + 100
    home = evaluation.conditions[4]
    assert home.seed_list() == [9100, 9101]  # the training runs' own seeds
    configs = evaluation.configs()
    for seed in (9100, 9101):
        away = configs[("evolved", seed + 100)]
        # Independently re-derive the sample: survivors by ID, default_rng(eval seed).choice.
        survivors = e007.query_df(
            "SELECT b.* EXCLUDE (run_id, organism_id) FROM brains b JOIN organisms o "
            "USING (run_id, organism_id) JOIN runs r USING (run_id) "
            "WHERE r.seed = $s AND o.alive ORDER BY b.organism_id",
            lake,
            {"s": seed},
        ).to_numpy()
        picks = np.random.default_rng(seed + 100).choice(len(survivors), 30, replace=False)
        assert away.brain.founder_weights == survivors[picks].tolist()
        assert configs[("home", seed)].brain.founder_weights == away.brain.founder_weights
        assert away.organisms.max_population == away.organisms.initial_count == 30
        assert not away.mutation.enabled
        assert not away.run.stop_on_extinction and away.run.max_ticks == 50
        # The primary endpoint sums behaviour.n over every tick, so the training spec's
        # sampling (ticks_every 10) must not leak into the evaluation runs.
        assert away.recording.ticks_every == 1
    assert configs[("seeker", 9200)].organisms.controller == "nearest_food_seeker"
    assert configs[("random_brains", 9200)].brain.founder_weights is None


def test_e007_results_figures_build_from_metrics():
    import sys

    sys.path.insert(0, str(EXPERIMENTS))
    report = load("e007_report")
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        [
            {"condition": c, "world": w, "meal_rate": rng.uniform(0.02, 0.07)}
            for c in report.LABELS
            for w in range(6)
        ]
    )
    outcomes = report.outcomes_figure(df)
    assert len(outcomes.data) == 2 * len(report.LABELS)  # dots + mean bar per condition
    diff = pd.Series(rng.normal(0.002, 0.001, 6), index=range(6))
    differences = report.differences_figure(diff, (0.001, 0.003), 0.0033)
    assert list(differences.data[0].y) == sorted(diff)

"""The pre-registered E004-E006 analyses, checked on synthetic data with known answers.

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

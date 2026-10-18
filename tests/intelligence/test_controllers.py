"""Tests for the baseline controllers and the controller registry."""

from typing import get_args

import numpy as np
import pytest

from genesis.core.config import ControllerName
from genesis.intelligence.controllers import (
    CONTROLLERS,
    NearestFoodSeeker,
    RandomWalk,
    make_controller,
)
from genesis.intelligence.sensors import Observations


def observations(found, bearing) -> Observations:
    found = np.array(found, dtype=bool)
    n = len(found)
    return Observations(
        food_found=found,
        food_distance=np.where(found, 5.0, np.inf),
        food_bearing=np.array(bearing, dtype=float),
        energy=np.full(n, 50.0),
    )


def test_registry_matches_config_choices():
    # The config's allowed names and the registry must never drift apart.
    assert set(CONTROLLERS) == set(get_args(ControllerName))


@pytest.mark.parametrize("name", sorted(CONTROLLERS))
def test_make_controller_builds_each_registered_controller(name):
    assert isinstance(make_controller(name), CONTROLLERS[name])


def test_make_controller_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown controller"):
        make_controller("telepathic")


def test_seeker_turns_by_the_bearing_when_food_is_sensed():
    obs = observations(found=[True, True], bearing=[0.4, -1.2])
    actions = NearestFoodSeeker().decide(obs, np.random.default_rng(0))
    np.testing.assert_array_equal(actions.turn, [0.4, -1.2])


def test_seeker_without_food_wanders_exactly_like_random_walk():
    # Same seed, no food sensed: identical turns. This is what makes RandomWalk a fair control.
    obs = observations(found=[False, False, False], bearing=[0, 0, 0])
    seeker = NearestFoodSeeker().decide(obs, np.random.default_rng(5))
    walker = RandomWalk().decide(obs, np.random.default_rng(5))
    np.testing.assert_array_equal(seeker.turn, walker.turn)


def test_seeker_mixed_population():
    obs = observations(found=[True, False], bearing=[0.4, 0.0])
    actions = NearestFoodSeeker().decide(obs, np.random.default_rng(0))
    assert actions.turn[0] == 0.4
    assert actions.turn[1] != 0.0  # a random wander turn


def test_random_walk_ignores_food():
    rng_a, rng_b = np.random.default_rng(9), np.random.default_rng(9)
    with_food = RandomWalk().decide(observations([True, True], [1.0, -1.0]), rng_a)
    no_food = RandomWalk().decide(observations([False, False], [0.0, 0.0]), rng_b)
    np.testing.assert_array_equal(with_food.turn, no_food.turn)


@pytest.mark.parametrize("controller", [RandomWalk(), NearestFoodSeeker()])
def test_baselines_always_move_at_full_speed(controller):
    actions = controller.decide(observations([True, False], [0.5, 0.0]), np.random.default_rng(0))
    np.testing.assert_array_equal(actions.throttle, [1.0, 1.0])


@pytest.mark.parametrize("controller", [RandomWalk(), NearestFoodSeeker()])
def test_same_seed_same_decisions(controller):
    obs = observations([False] * 10, [0.0] * 10)
    a = controller.decide(obs, np.random.default_rng(3))
    b = controller.decide(obs, np.random.default_rng(3))
    np.testing.assert_array_equal(a.turn, b.turn)


@pytest.mark.parametrize("controller", [RandomWalk(), NearestFoodSeeker()])
def test_empty_population(controller):
    actions = controller.decide(observations([], []), np.random.default_rng(0))
    assert len(actions.turn) == 0 and len(actions.throttle) == 0


def test_random_walk_turn_spread_matches_setting():
    obs = observations([False] * 20_000, [0.0] * 20_000)
    actions = RandomWalk(turn_sd=0.3).decide(obs, np.random.default_rng(1))
    assert np.std(actions.turn) == pytest.approx(0.3, abs=0.01)
    assert np.mean(actions.turn) == pytest.approx(0.0, abs=0.01)

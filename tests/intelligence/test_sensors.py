"""Tests for sense_food: range, nearest selection, bearings, and empty cases."""

import numpy as np
import pytest

from genesis.intelligence.sensors import sense_food


def sense(positions, headings, food, sense_range=10.0, energies=None):
    """Helper: build arrays from plain lists and call sense_food."""
    positions = np.array(positions, dtype=float).reshape(-1, 2)
    n = len(positions)
    return sense_food(
        positions=positions,
        headings=np.array(headings, dtype=float),
        sense_ranges=np.full(n, sense_range),
        energies=np.full(n, 50.0) if energies is None else np.array(energies, dtype=float),
        food_positions=np.array(food, dtype=float).reshape(-1, 2),
    )


def test_food_dead_ahead_has_zero_bearing():
    obs = sense([[0, 0]], [0.0], food=[[5, 0]])
    assert obs.food_found[0]
    assert obs.food_distance[0] == pytest.approx(5.0)
    assert obs.food_bearing[0] == pytest.approx(0.0)


def test_food_to_the_left_has_positive_bearing():
    # Facing +x; food at +y is a quarter turn counter-clockwise, i.e. to the left.
    obs = sense([[0, 0]], [0.0], food=[[0, 5]])
    assert obs.food_bearing[0] == pytest.approx(np.pi / 2)


def test_bearing_is_relative_to_heading():
    # Same food at +y, but the organism already faces +y: the food is now dead ahead.
    obs = sense([[0, 0]], [np.pi / 2], food=[[0, 5]])
    assert obs.food_bearing[0] == pytest.approx(0.0)


def test_food_behind_has_bearing_near_pi():
    obs = sense([[0, 0]], [0.0], food=[[-5, 0]])
    assert abs(obs.food_bearing[0]) == pytest.approx(np.pi)


def test_food_out_of_range_is_not_sensed():
    obs = sense([[0, 0]], [0.0], food=[[50, 0]], sense_range=10.0)
    assert not obs.food_found[0]
    assert obs.food_distance[0] == np.inf
    assert obs.food_bearing[0] == 0.0


def test_food_exactly_at_range_is_sensed():
    obs = sense([[0, 0]], [0.0], food=[[10, 0]], sense_range=10.0)
    assert obs.food_found[0]


def test_nearest_of_several_is_chosen():
    obs = sense([[0, 0]], [0.0], food=[[8, 0], [0, 3], [6, 6]])
    assert obs.food_distance[0] == pytest.approx(3.0)
    assert obs.food_bearing[0] == pytest.approx(np.pi / 2)


def test_equidistant_food_picks_lower_index():
    obs = sense([[0, 0]], [0.0], food=[[0, 5], [0, -5]])  # left vs right, both 5 away
    assert obs.food_bearing[0] == pytest.approx(np.pi / 2)  # index 0, the one on the left


def test_each_organism_uses_its_own_sense_range():
    obs = sense_food(
        positions=np.array([[0.0, 0.0], [0.0, 0.0]]),
        headings=np.zeros(2),
        sense_ranges=np.array([5.0, 20.0]),
        energies=np.zeros(2),
        food_positions=np.array([[10.0, 0.0]]),
    )
    np.testing.assert_array_equal(obs.food_found, [False, True])


def test_many_organisms_sensed_independently():
    obs = sense([[0, 0], [100, 100]], [0.0, 0.0], food=[[3, 0]], sense_range=10.0)
    np.testing.assert_array_equal(obs.food_found, [True, False])


def test_no_food_in_world():
    obs = sense([[0, 0], [5, 5]], [0.0, 0.0], food=np.empty((0, 2)))
    assert not obs.food_found.any()
    assert len(obs) == 2


def test_no_organisms():
    obs = sense(np.empty((0, 2)), [], food=[[1, 1]])
    assert len(obs) == 0


def test_energy_is_passed_through_as_a_copy():
    energies = np.array([42.0])
    obs = sense_food(
        positions=np.zeros((1, 2)),
        headings=np.zeros(1),
        sense_ranges=np.ones(1),
        energies=energies,
        food_positions=np.empty((0, 2)),
    )
    energies[0] = 0.0  # changing the source afterwards must not change the observation
    assert obs.energy[0] == 42.0

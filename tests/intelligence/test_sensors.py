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


# --- Large populations use the spatial grid; the answer must not change ----------------------


def sense_all_pairs(positions, headings, sense_ranges, energies, food, monkeypatch):
    """sense_food with the grid switched off (every pair computed), the reference answer."""
    from genesis.core import spatial

    monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", float("inf"))
    try:
        return sense_food(positions, headings, sense_ranges, energies, food)
    finally:
        monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", 4096)


def assert_identical_observations(a, b):
    for field in ("food_found", "food_distance", "food_bearing", "energy"):
        x, y = getattr(a, field), getattr(b, field)
        assert x.dtype == y.dtype
        assert np.array_equal(x, y), field


@pytest.mark.parametrize("seed", range(6))
def test_grid_sensing_is_bit_identical_to_all_pairs(seed, monkeypatch):
    rng = np.random.default_rng(seed)
    n, m = rng.integers(200, 1500), rng.integers(50, 400)
    positions = rng.uniform(0, 200, (n, 2))
    headings = rng.uniform(-np.pi, np.pi, n)
    sense_ranges = rng.uniform(1.0, 60.0, n) if seed % 2 else np.full(n, 20.0)
    energies = rng.uniform(0, 100, n)
    food = rng.uniform(0, 200, (m, 2))
    grid = sense_food(positions, headings, sense_ranges, energies, food)
    reference = sense_all_pairs(positions, headings, sense_ranges, energies, food, monkeypatch)
    assert_identical_observations(grid, reference)


def test_grid_sensing_breaks_exact_ties_by_lower_index_like_all_pairs(monkeypatch):
    # 100 organisms at integer points; food at exactly 1 unit left and right of each: ties.
    centres = np.array([(float(x), 50.0) for x in range(0, 300, 3)])
    left, right = centres - [1.0, 0.0], centres + [1.0, 0.0]
    food = np.vstack([right, left])  # "right" has the lower index for every organism
    headings = np.zeros(len(centres))
    sense = np.full(len(centres), 2.0)
    energies = np.zeros(len(centres))
    assert len(centres) * len(food) > 4096  # the grid path is in use
    grid = sense_food(centres, headings, sense, energies, food)
    reference = sense_all_pairs(centres, headings, sense, energies, food, monkeypatch)
    assert_identical_observations(grid, reference)
    assert np.all(grid.food_bearing == 0.0)  # faced +x, chose the right-hand item (index wins)

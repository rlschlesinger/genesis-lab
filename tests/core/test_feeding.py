"""Tests for food contention: reach, closest-first matching, fair tie-breaking."""

import numpy as np
import pytest

from genesis.core.feeding import resolve_feeding

RADIUS = 2.0


def feed(organisms, food, seed=0):
    return resolve_feeding(
        np.array(organisms, dtype=float).reshape(-1, 2),
        np.array(food, dtype=float).reshape(-1, 2),
        RADIUS,
        np.random.default_rng(seed),
    )


def as_pairs(meals):
    return sorted(zip(meals.eaters.tolist(), meals.foods.tolist(), strict=True))


def test_food_within_reach_is_eaten():
    assert as_pairs(feed([[0, 0]], [[1.5, 0]])) == [(0, 0)]


def test_food_exactly_at_radius_is_eaten():
    assert as_pairs(feed([[0, 0]], [[2.0, 0]])) == [(0, 0)]


def test_food_out_of_reach_is_not_eaten():
    assert len(feed([[0, 0]], [[2.01, 0]])) == 0


def test_closer_organism_wins_contested_food():
    # Organism 1 is closer (0.5 vs 1.5), even though organism 0 has the lower index.
    assert as_pairs(feed([[0, 0], [1.0, 0]], [[1.5, 0]])) == [(1, 0)]


def test_organism_eats_at_most_one_item_per_tick():
    meals = feed([[0, 0]], [[0.5, 0], [1.0, 0], [0, 1.5]])
    assert as_pairs(meals) == [(0, 0)]  # only the closest


def test_greedy_matching_feeds_everyone_it_can():
    # A (0) is near f1 (0.5) and f2 (1.0); B (1) can only reach f2.
    # Closest-first: A takes f1, then B takes f2. Both eat.
    organisms = [[0, 0], [2.5, 0]]
    food = [[-0.5, 0], [1.0, 0]]
    assert as_pairs(feed(organisms, food)) == [(0, 0), (1, 1)]


def test_exact_tie_is_decided_by_seed_not_id():
    # Two organisms exactly 1.0 from the food, on opposite sides: a perfect tie.
    organisms, food = [[-1.0, 0], [1.0, 0]], [[0, 0]]
    winners = [int(feed(organisms, food, seed=s).eaters[0]) for s in range(400)]
    # Same seed, same winner (reproducible)...
    assert winners[:10] == [int(feed(organisms, food, seed=s).eaters[0]) for s in range(10)]
    # ...but across seeds each wins about half the time. Breaking ties by ID would make
    # organism 0 win all 400. The bounds are about 5 standard deviations from 200.
    assert 150 < winners.count(0) < 250


def test_every_item_and_every_organism_used_at_most_once():
    rng = np.random.default_rng(1)
    organisms = rng.uniform(0, 10, size=(60, 2))  # crowded: lots of contention
    food = rng.uniform(0, 10, size=(40, 2))
    meals = resolve_feeding(organisms, food, RADIUS, np.random.default_rng(2))
    assert len(set(meals.eaters.tolist())) == len(meals)
    assert len(set(meals.foods.tolist())) == len(meals)
    assert len(meals) > 0


def test_every_meal_is_within_reach():
    rng = np.random.default_rng(3)
    organisms, food = rng.uniform(0, 10, size=(30, 2)), rng.uniform(0, 10, size=(30, 2))
    meals = resolve_feeding(organisms, food, RADIUS, np.random.default_rng(4))
    gaps = np.hypot(*(organisms[meals.eaters] - food[meals.foods]).T)
    assert (gaps <= RADIUS).all()


def test_empty_inputs():
    assert len(feed(np.empty((0, 2)), [[0, 0]])) == 0
    assert len(feed([[0, 0]], np.empty((0, 2)))) == 0


# --- Large populations use the spatial grid; the meals must not change -----------------------


def feed_all_pairs(organisms, food, rng, monkeypatch):
    """resolve_feeding with the grid switched off, the reference answer."""
    from genesis.core import spatial

    monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", float("inf"))
    try:
        return resolve_feeding(organisms, food, RADIUS, rng)
    finally:
        monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", 4096)


@pytest.mark.parametrize("seed", range(6))
def test_grid_feeding_is_bit_identical_to_all_pairs(seed, monkeypatch):
    rng = np.random.default_rng(seed)
    n, m = rng.integers(200, 2000), rng.integers(50, 500)
    size = 40.0 if seed % 2 else 200.0  # a small world makes a crowded one
    organisms, food = rng.uniform(0, size, (n, 2)), rng.uniform(0, size, (m, 2))
    grid = resolve_feeding(organisms, food, RADIUS, np.random.default_rng(seed + 100))
    reference = feed_all_pairs(organisms, food, np.random.default_rng(seed + 100), monkeypatch)
    assert np.array_equal(grid.eaters, reference.eaters)
    assert np.array_equal(grid.foods, reference.foods)
    assert len(grid) > 0


def test_grid_feeding_resolves_exact_ties_like_all_pairs(monkeypatch):
    # Organisms on a lattice, food exactly half-way between neighbours: every pair is a tie,
    # so the outcome depends entirely on the tiebreak draws being assigned to the same pairs.
    xs = np.arange(0.0, 60.0, 3.0)
    organisms = np.array([(x, y) for x in xs for y in xs])
    food = organisms + np.array([1.5, 0.0])
    assert len(organisms) * len(food) > 4096
    for seed in range(5):
        grid = resolve_feeding(organisms, food, RADIUS, np.random.default_rng(seed))
        reference = feed_all_pairs(organisms, food, np.random.default_rng(seed), monkeypatch)
        assert np.array_equal(grid.eaters, reference.eaters)
        assert np.array_equal(grid.foods, reference.foods)

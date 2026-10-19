"""Unit tests for parent selection and offspring placement."""

import numpy as np

from genesis.core.resources import FoodSupply
from genesis.core.world import World
from genesis.evolution.reproduction import place_offspring, select_parents


def rng(seed=0):
    return np.random.default_rng(seed)


# --- select_parents -----------------------------------------------------------------------


def test_everyone_eligible_reproduces_when_there_is_room():
    eligible = np.array([True, False, True, True])
    np.testing.assert_array_equal(select_parents(eligible, room=10, rng=rng()), [0, 2, 3])


def test_no_room_means_no_parents():
    assert len(select_parents(np.array([True, True]), room=0, rng=rng())) == 0


def test_nobody_eligible_means_no_parents():
    assert len(select_parents(np.array([False, False]), room=5, rng=rng())) == 0


def test_limited_room_picks_exactly_that_many_eligible_unique_sorted():
    eligible = np.array([True, False] * 10)  # 10 eligible, at even indices
    chosen = select_parents(eligible, room=4, rng=rng())
    assert len(chosen) == 4
    assert len(set(chosen.tolist())) == 4
    assert eligible[chosen].all()
    assert (np.diff(chosen) > 0).all()  # ascending


def test_limited_room_is_random_not_lowest_index_first():
    # 10 eligible, room for 1, over 1000 seeds. "First in the list" would pick index 0
    # every time; uniform choice picks it about 100 times (sd ~9.5, so 60-140 is ~4 sd).
    eligible = np.ones(10, dtype=bool)
    picks = [int(select_parents(eligible, room=1, rng=rng(s))[0]) for s in range(1000)]
    assert 60 < picks.count(0) < 140
    assert len(set(picks)) == 10  # every candidate gets chosen sometimes


def test_same_seed_same_parents():
    eligible = np.ones(20, dtype=bool)
    a = select_parents(eligible, room=5, rng=rng(7))
    b = select_parents(eligible, room=5, rng=rng(7))
    np.testing.assert_array_equal(a, b)


# --- place_offspring ----------------------------------------------------------------------


def world() -> World:
    return World(100.0, 100.0, FoodSupply(100.0, 100.0, max_count=1, regrowth_per_tick=0.0))


def test_offspring_appear_within_max_distance_of_parent():
    parents = np.full((500, 2), 50.0)
    positions, headings = place_offspring(parents, np.full(500, 1.5), world(), rng())
    gaps = np.hypot(*(positions - parents).T)
    assert (gaps <= 1.5 + 1e-12).all()
    assert ((headings >= -np.pi) & (headings < np.pi)).all()


def test_offspring_spread_evenly_over_the_disc():
    # With even spreading, the inner half of the radius holds a quarter of the area, so it
    # should get about a quarter of the births (not half, as it would without the sqrt).
    parents = np.full((20_000, 2), 50.0)
    positions, _ = place_offspring(parents, np.full(20_000, 2.0), world(), rng(1))
    gaps = np.hypot(*(positions - parents).T)
    assert abs(np.mean(gaps < 1.0) - 0.25) < 0.02


def test_offspring_of_a_parent_in_a_corner_stay_inside_the_walls():
    w = world()
    parents = np.zeros((200, 2))
    positions, _ = place_offspring(parents, np.full(200, 1.5), w, rng())
    assert w.contains(positions).all()


def test_no_parents_no_offspring():
    positions, headings = place_offspring(np.empty((0, 2)), np.empty(0), world(), rng())
    assert positions.shape == (0, 2) and len(headings) == 0

"""Tests for FoodSupply: spawning, the cap, regrowth statistics, removal, read-only views."""

import numpy as np
import pytest

from genesis.core.resources import FoodSupply

W, H = 100.0, 50.0


def make_supply(max_count: int = 1000, rate: float = 2.0) -> FoodSupply:
    return FoodSupply(W, H, max_count=max_count, regrowth_per_tick=rate)


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_starts_empty_with_correct_shape():
    supply = make_supply()
    assert supply.count == 0
    assert supply.positions.shape == (0, 2)


def test_spawn_places_food_inside_bounds():
    supply = make_supply()
    added = supply.spawn(500, rng())
    assert added == 500
    xs, ys = supply.positions[:, 0], supply.positions[:, 1]
    assert xs.min() >= 0 and xs.max() < W
    assert ys.min() >= 0 and ys.max() < H


def test_spawn_never_exceeds_cap():
    supply = make_supply(max_count=10)
    assert supply.spawn(25, rng()) == 10  # returns what was actually added, not requested
    assert supply.spawn(5, rng()) == 0
    assert supply.count == 10


def test_regrowth_respects_cap_over_many_ticks():
    supply = make_supply(max_count=50, rate=20.0)
    generator = rng()
    for _ in range(200):
        supply.regrow(generator)
        assert supply.count <= 50
    assert supply.count == 50


def test_zero_regrowth_adds_nothing():
    supply = make_supply(rate=0.0)
    generator = rng()
    assert sum(supply.regrow(generator) for _ in range(100)) == 0


def test_regrowth_mean_matches_configured_rate():
    # Poisson(2.0) averaged over 5000 ticks has standard error sqrt(2/5000) ~ 0.02, so a
    # tolerance of 0.1 is about 5 standard errors. The seed is fixed, so this test gives
    # the same answer on every run; it is not flaky.
    supply = make_supply(max_count=10**6, rate=2.0)
    generator = rng(123)
    counts = [supply.regrow(generator) for _ in range(5000)]
    assert np.mean(counts) == pytest.approx(2.0, abs=0.1)


def test_same_seed_gives_identical_food():
    a, b = make_supply(), make_supply()
    a.spawn(100, rng(7))
    b.spawn(100, rng(7))
    np.testing.assert_array_equal(a.positions, b.positions)


def test_different_seeds_give_different_food():
    a, b = make_supply(), make_supply()
    a.spawn(100, rng(7))
    b.spawn(100, rng(8))
    assert not np.array_equal(a.positions, b.positions)


def test_remove_deletes_exactly_those_items_and_keeps_order():
    supply = make_supply()
    supply.spawn(5, rng())
    before = supply.positions.copy()
    supply.remove([1, 3])
    np.testing.assert_array_equal(supply.positions, before[[0, 2, 4]])


def test_remove_nothing_is_a_no_op():
    supply = make_supply()
    supply.spawn(3, rng())
    supply.remove([])
    assert supply.count == 3


@pytest.mark.parametrize("bad", [[5], [-1]])
def test_remove_out_of_range_raises(bad):
    supply = make_supply()
    supply.spawn(5, rng())
    with pytest.raises(IndexError):
        supply.remove(bad)


def test_remove_duplicate_index_raises():
    # Guards the energy ledger: two organisms must never both be credited for one item.
    supply = make_supply()
    supply.spawn(5, rng())
    with pytest.raises(ValueError, match="duplicate"):
        supply.remove([2, 2])


def test_positions_view_is_read_only():
    supply = make_supply()
    supply.spawn(3, rng())
    with pytest.raises(ValueError, match="read-only"):
        supply.positions[0, 0] = 999.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_count": 0},
        {"rate": -1.0},
    ],
)
def test_invalid_construction_rejected(kwargs):
    with pytest.raises(ValueError):
        make_supply(**kwargs)


def test_negative_spawn_rejected():
    with pytest.raises(ValueError):
        make_supply().spawn(-1, rng())

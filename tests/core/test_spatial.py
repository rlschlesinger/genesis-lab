"""Tests for the spatial grid: it must give exactly the all-pairs answer, only faster.

The all-pairs functions (``dense_pairs``, and the matrix branch of ``nearest_within_reach``)
are the reference. Every test here checks the grid against them *bit for bit*: same pairs, same
order, same distances, same dtypes. Random inputs cover typical worlds; the hand-built cases
cover the places where a grid can go wrong (cell boundaries, exact reach, duplicates, odd
coordinates); hypothesis searches for anything else and shrinks a failure to a small example.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from genesis.core import spatial
from genesis.core.spatial import (
    DENSE_PAIR_LIMIT,
    _grid_pairs,
    dense_pairs,
    nearest_within_reach,
    pairs_within_reach,
)


def assert_same_pairs(expected, actual):
    for e, a in zip(expected, actual, strict=True):
        assert e.dtype == a.dtype
        assert np.array_equal(e, a), f"{e} != {a}"


def nearest_dense(points, reach, targets):
    """The matrix branch of nearest_within_reach, forced regardless of size."""
    n = len(points)
    offsets = targets[np.newaxis, :, :] - points[:, np.newaxis, :]
    distances = np.hypot(offsets[..., 0], offsets[..., 1])
    distances = np.where(distances <= reach[:, np.newaxis], distances, np.inf)
    nearest = np.argmin(distances, axis=1)
    return nearest, distances[np.arange(n), nearest]


def check_grid(points, reach, targets):
    """Run the grid and compare it with the references. Returns False if the grid declined."""
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    targets = np.asarray(targets, dtype=float).reshape(-1, 2)
    reach = np.broadcast_to(np.asarray(reach, dtype=float), (len(points),)).copy()
    grid = _grid_pairs(points, reach, targets)
    if grid is None:
        return False
    assert_same_pairs(dense_pairs(points, reach, targets), grid)
    # The nearest-target selection on top of the grid pairs vs the matrix.
    n, m = len(points), len(targets)
    if n * m > DENSE_PAIR_LIMIT:
        expected = nearest_dense(points, reach, targets)
        actual = nearest_within_reach(points, reach, targets)
        assert_same_pairs(expected, actual)
    return True


# --- Random worlds --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "m", "reach"),
    [
        (100, 110, 2.0),
        (100, 110, 20.0),
        (300, 160, 20.0),
        (1000, 260, 2.0),
        (1000, 260, 20.0),
        (260, 1000, 20.0),  # more targets than points: the other side scans
        (3000, 180, 2.0),
        (3000, 180, 20.0),
        (3000, 3000, 2.0),
    ],
)
def test_grid_matches_all_pairs_on_random_worlds(n, m, reach):
    rng = np.random.default_rng(n * 7 + m)
    points = rng.uniform(0, 200, (n, 2))
    targets = rng.uniform(0, 200, (m, 2))
    assert check_grid(points, reach, targets)


def test_grid_matches_with_a_different_reach_per_point():
    rng = np.random.default_rng(11)
    points, targets = rng.uniform(0, 200, (800, 2)), rng.uniform(0, 200, (300, 2))
    reach = rng.uniform(1.0, 30.0, 800)  # like evolved sense ranges
    assert check_grid(points, reach, targets)


def test_many_seeds_small_crowded_worlds():
    # Dense crowds in a small world: many pairs per organism, many near-ties.
    for seed in range(40):
        rng = np.random.default_rng(seed)
        n, m = rng.integers(1, 90), rng.integers(1, 90)
        points = rng.uniform(0, 12, (n, 2)).round(1)  # rounding creates exact duplicates
        targets = rng.uniform(0, 12, (m, 2)).round(1)
        check_grid(points, rng.uniform(0.5, 4.0, n), targets)


# --- The places where a grid can go wrong -----------------------------------------------------


def test_points_exactly_on_cell_boundaries():
    r = 2.0
    grid_lines = np.arange(0, 40, r, dtype=float)  # multiples of the cell size
    points = np.array([(x, y) for x in grid_lines for y in grid_lines])
    targets = points + np.array([r, 0.0])  # exactly one reach away, along a cell edge
    targets = np.vstack([targets, points, points + np.array([0.0, -r])])
    assert check_grid(points, r, targets)


def test_targets_exactly_at_reach_in_every_direction():
    # 60 points far apart, each ringed by 36 targets at exactly the reach: the exact
    # "<= reach" test decides every pair, and the grid must agree on each one.
    angles = np.linspace(-np.pi, np.pi, 36, endpoint=False)
    points = np.array([(20.0 * k, 50.0) for k in range(60)])
    ring = 7.5 * np.column_stack([np.cos(angles), np.sin(angles)])
    targets = (points[:, np.newaxis, :] + ring[np.newaxis, :, :]).reshape(-1, 2)
    assert check_grid(points, 7.5, targets)
    # Including when the reach is a hair smaller, so most are just out of reach.
    assert check_grid(points, np.nextafter(7.5, 0), targets)


def test_everything_in_one_cell_declines_and_everything_far_apart_works():
    rng = np.random.default_rng(5)
    clump = rng.uniform(0, 0.5, (120, 2))
    reach = np.full(120, 1.0)
    # One cell holds everything, so the grid would propose every pair: it declines, and the
    # public function falls back to the all-pairs code.
    assert _grid_pairs(clump, reach, clump) is None
    assert_same_pairs(dense_pairs(clump, reach, clump), pairs_within_reach(clump, reach, clump))
    spread = rng.uniform(0, 1e6, (120, 2))
    assert check_grid(spread, 1.0, spread)  # no pairs except each item with itself


def test_duplicate_positions_and_zero_distances():
    points = np.repeat([[3.0, 3.0], [9.0, 9.0]], 60, axis=0)
    targets = np.repeat([[3.0, 3.0], [9.0, 9.0], [3.0, 4.0]], 30, axis=0)
    assert check_grid(points, 1.0, targets)


def test_negative_and_mixed_sign_coordinates():
    rng = np.random.default_rng(6)
    points = rng.uniform(-50, 50, (200, 2))
    targets = rng.uniform(-50, 50, (200, 2))
    assert check_grid(points, 3.0, targets)


def test_grid_declines_when_the_reach_covers_the_world():
    rng = np.random.default_rng(7)
    points, targets = rng.uniform(0, 10, (100, 2)), rng.uniform(0, 10, (100, 2))
    assert _grid_pairs(points, np.full(100, 100.0), targets) is None
    # And the public function still answers correctly, via the all-pairs path.
    assert_same_pairs(
        dense_pairs(points, np.full(100, 100.0), targets),
        pairs_within_reach(points, np.full(100, 100.0), targets),
    )


def test_zero_reach_and_empty_inputs():
    rng = np.random.default_rng(8)
    points, targets = rng.uniform(0, 10, (100, 2)), rng.uniform(0, 10, (100, 2))
    zero = np.zeros(100)
    assert_same_pairs(dense_pairs(points, zero, targets), pairs_within_reach(points, zero, targets))
    empty = np.empty((0, 2))
    i, j, d = pairs_within_reach(empty, np.empty(0), targets)
    assert (len(i), len(j), len(d)) == (0, 0, 0) and i.dtype == np.intp
    nearest, distance = nearest_within_reach(points, zero, empty)
    assert np.all(np.isinf(distance)) and np.all(nearest == 0)


def test_public_function_uses_all_pairs_for_small_inputs(monkeypatch):
    calls = []
    original = spatial._grid_pairs
    monkeypatch.setattr(spatial, "_grid_pairs", lambda *a: calls.append(1) or original(*a))
    rng = np.random.default_rng(9)
    small, big = rng.uniform(0, 10, (10, 2)), rng.uniform(0, 10, (100, 2))
    pairs_within_reach(small, np.full(10, 1.0), small)
    assert calls == []  # 100 pairs: below DENSE_PAIR_LIMIT
    pairs_within_reach(big, np.full(100, 1.0), big)
    assert calls == [1]


# --- Property-based: let hypothesis look for a counter-example -------------------------------

coordinates = st.floats(min_value=-20.0, max_value=120.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=300, deadline=None)
@given(
    points=hnp.arrays(np.float64, st.tuples(st.integers(1, 40), st.just(2)), elements=coordinates),
    targets=hnp.arrays(np.float64, st.tuples(st.integers(1, 40), st.just(2)), elements=coordinates),
    reach=st.floats(min_value=0.01, max_value=30.0),
    per_point=st.booleans(),
)
def test_grid_never_disagrees_with_all_pairs(points, targets, reach, per_point):
    n = len(points)
    reaches = np.linspace(reach / 3, reach, n) if per_point else np.full(n, reach)
    check_grid(points, reaches, targets)  # declining is allowed; disagreeing is not

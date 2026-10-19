"""Spatial grid: find every (organism, food) pair within reach without checking every pair.

The problem. Sensing and feeding both ask "which food items are within distance r of each
organism?". The direct answer compares every organism with every food item: n x m distances
per tick. At 30 organisms and 70 food items that is 2,100 distances, nothing. At 3,000
organisms and 300 food items it is 900,000, and the two calls take two thirds of a tick
(docs/benchmarks.md, D-017).

The idea. Cut the world into square cells with side ``cell`` at least as long as the longest
reach. Food within reach of an organism can only lie in the organism's own cell or the ring of
cells around it, so only food in those few cells needs its distance measured. With the default
sense range (20 units in a 200 x 200 world) that is about 9% of the food; with the eat radius
(2 units) it is almost none.

Bit-identical by construction. The grid is only a *filter* that proposes candidate pairs. It
never decides anything: every candidate's distance is then computed with the same NumPy
``hypot`` call on the same offsets as the all-pairs code, and the same ``<=`` test is applied.
The grid proposes a *superset* of the true pairs (see ``_grid_pairs``), so the pairs that
survive the exact test are exactly the all-pairs result, in the same order
(``tests/core/test_spatial.py`` checks this against the all-pairs version on random and
adversarial inputs). One NumPy-specific fact makes this work: on a given machine, ``hypot``
gives the same bits for the same pair of numbers whether they sit in a big (n, m) matrix or
in a short list of candidates. That was measured before relying on it (D-036).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.intp]

# Below this many organism x food pairs the all-pairs code is faster than building a grid
# (the grid has a fixed cost of ~100 microseconds). Measured in docs/benchmarks.md.
DENSE_PAIR_LIMIT = 4096
# If the grid would still propose more than this share of all pairs (very long reach compared
# with the world), it saves nothing: use the all-pairs code instead.
DENSE_FRACTION = 0.5


def pairs_within_reach(
    points: FloatArray, reach: FloatArray, targets: FloatArray
) -> tuple[IntArray, IntArray, FloatArray]:
    """Every pair (i, j) with ``hypot(targets[j] - points[i]) <= reach[i]``.

    Shapes: ``points`` (n, 2), ``reach`` (n,), ``targets`` (m, 2). Returns three arrays of
    equal length: point indices ``i``, target indices ``j`` and the exact distances, ordered
    by ``i`` then ``j`` (the order ``np.nonzero`` gives on the all-pairs matrix).

    Chooses between the all-pairs computation and the grid purely on speed; the result is
    the same either way.
    """
    n, m = len(points), len(targets)
    reach = np.asarray(reach, dtype=np.float64)
    if n == 0 or m == 0:
        return _no_pairs()
    if n * m <= DENSE_PAIR_LIMIT:
        return dense_pairs(points, reach, targets)
    result = _grid_pairs(points, reach, targets)
    if result is None:  # the grid would check most pairs anyway
        return dense_pairs(points, reach, targets)
    return result


def nearest_within_reach(
    points: FloatArray, reach: FloatArray, targets: FloatArray
) -> tuple[IntArray, FloatArray]:
    """For each point, the index of its nearest target within reach and the distance to it.

    Returns ``(nearest (n,), distance (n,))``. A point with no target in reach gets distance
    ``inf`` and index 0 (a placeholder the caller must mask out). Equidistant targets: the
    lower index wins. Same result from the all-pairs matrix and from the grid.
    """
    n, m = len(points), len(targets)
    reach = np.asarray(reach, dtype=np.float64)
    nearest = np.zeros(n, dtype=np.intp)
    distance = np.full(n, np.inf)
    if n == 0 or m == 0:
        return nearest, distance
    pairs = _grid_pairs(points, reach, targets) if n * m > DENSE_PAIR_LIMIT else None
    if pairs is None:
        # Reference: (n, m) distances, out-of-reach ones set to inf, then the row minimum.
        # np.argmin returns the first minimum, so the lowest index wins exact ties.
        distances = _all_distances(points, targets)
        distances = np.where(distances <= reach[:, np.newaxis], distances, np.inf)
        nearest = np.argmin(distances, axis=1)
        return nearest, distances[np.arange(n), nearest]
    i, j, d = pairs
    if len(i) == 0:
        return nearest, distance
    # Pairs arrive ordered by (point, target). A *stable* sort by distance keeps that order
    # among equal distances, so the first pair of each point is its nearest target, lowest
    # index first on ties: the same choice np.argmin makes on the matrix.
    by_distance = np.argsort(d, kind="stable")
    points_seen, first = np.unique(i[by_distance], return_index=True)
    chosen = by_distance[first]
    nearest[points_seen] = j[chosen]
    distance[points_seen] = d[chosen]
    return nearest, distance


def dense_pairs(
    points: FloatArray, reach: FloatArray, targets: FloatArray
) -> tuple[IntArray, IntArray, FloatArray]:
    """The reference: every distance at once via broadcasting."""
    if len(points) == 0 or len(targets) == 0:
        return _no_pairs()
    distances = _all_distances(points, targets)
    i, j = np.nonzero(distances <= np.asarray(reach, dtype=np.float64)[:, np.newaxis])
    return i, j, distances[i, j]


def _all_distances(points: FloatArray, targets: FloatArray) -> FloatArray:
    """The (n, m) table of every point-to-target distance.

    Broadcasting: a row of m target x's minus a column of n point x's gives an (n, m) table
    of x offsets; the same for y; ``hypot`` combines them. Entry (i, j) is the offset from
    point i to target j, exactly the subtraction the grid performs for its candidate pairs.
    (Two 2-D tables are cheaper than one (n, m, 2) block that is then sliced in two.)
    """
    dx = targets[:, 0] - points[:, 0, np.newaxis]
    dy = targets[:, 1] - points[:, 1, np.newaxis]
    return np.hypot(dx, dy)


def _no_pairs() -> tuple[IntArray, IntArray, FloatArray]:
    empty = np.empty(0, dtype=np.intp)
    return empty, empty, np.empty(0, dtype=np.float64)


def _grid_pairs(
    points: FloatArray, reach: FloatArray, targets: FloatArray
) -> tuple[IntArray, IntArray, FloatArray] | None:
    """Candidate pairs from a grid, then the exact test. None if the grid saves nothing.

    The side with fewer items *scans*: each of its items looks up the cells its reach could
    touch. The other side is *bucketed*: its items are sorted by cell, so the items in one
    cell are one contiguous slice, found with a binary search (``np.searchsorted``).

    Why the candidates are a superset of the true pairs: a target within reach r of point p
    has each coordinate within [p - r, p + r], so its cell index floor(coordinate / cell)
    lies between floor((p - r) / cell) and floor((p + r) / cell). Rounding in "p - r" or
    "/ cell" can only move a value by a hair, so the reach is padded by a few units in the
    last place before computing those bounds. Every cell in that range is scanned.
    """
    n, m = len(points), len(targets)
    cell = float(reach.max())
    if not cell > 0:
        return None
    # The padding covers rounding in (p +/- r) and in the division by the cell size.
    scale = max(float(np.abs(points).max()), float(np.abs(targets).max()), cell)
    pad = 8.0 * np.spacing(scale)

    if m <= n:
        # Targets scan with the longest reach (reach is per point, and a target does not know
        # which points are near); the exact test below applies each point's own reach.
        scan, bucket, half = targets, points, cell + pad
    else:
        scan, bucket, half = points, targets, (reach + pad)[:, np.newaxis]

    # Cell coordinates: one cell per bucketed item; a range of cells per scanning item.
    bucket_cells = np.floor(bucket / cell).astype(np.int64)  # (b, 2)
    lo = np.floor((scan - half) / cell).astype(np.int64)  # (s, 2)
    hi = np.floor((scan + half) / cell).astype(np.int64)  # (s, 2)

    # One integer key per cell: key = column * stride + row, with rows shifted to start at 0
    # so that the key is unique for every cell either side could touch.
    row_min = min(int(bucket_cells[:, 1].min()), int(lo[:, 1].min()))
    stride = max(int(bucket_cells[:, 1].max()), int(hi[:, 1].max())) - row_min + 1
    bucket_keys = bucket_cells[:, 0] * stride + (bucket_cells[:, 1] - row_min)
    # Stable sort: items with the same key stay in ascending index order.
    order = np.argsort(bucket_keys, kind="stable")
    sorted_keys = bucket_keys[order]

    # Enumerate every (scanning item, cell) combination: item s scans nx[s] * ny[s] cells.
    nx, ny = hi[:, 0] - lo[:, 0] + 1, hi[:, 1] - lo[:, 1] + 1
    cells_each = nx * ny
    total_cells = int(cells_each.sum())
    scanner = np.repeat(np.arange(len(scan), dtype=np.intp), cells_each)
    # Position of each combination within its item's block: 0, 1, ..., nx * ny - 1.
    local = np.arange(total_cells) - np.repeat(np.cumsum(cells_each) - cells_each, cells_each)
    ny_each = ny[scanner]
    col = lo[scanner, 0] + local // ny_each
    row = lo[scanner, 1] + local % ny_each
    keys = col * stride + (row - row_min)

    # Where each scanned cell's bucketed items sit in the sorted list: [left, right).
    left = np.searchsorted(sorted_keys, keys, side="left")
    counts = np.searchsorted(sorted_keys, keys, side="right") - left
    total = int(counts.sum())
    if total > DENSE_FRACTION * n * m:
        return None
    if total == 0:
        return _no_pairs()

    # Expand the (cell, [left, right)) slices into explicit candidate pairs.
    s = np.repeat(scanner, counts)
    within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    b = order[np.repeat(left, counts) + within]
    i, j = (b, s) if m <= n else (s, b)

    # The exact test, computed exactly as the all-pairs code does: offsets = target - point,
    # then hypot, then "<= reach".
    offsets = targets[j] - points[i]
    distances = np.hypot(offsets[:, 0], offsets[:, 1])
    keep = distances <= reach[i]
    i, j, distances = i[keep], j[keep], distances[keep]

    # Same order as np.nonzero on the (n, m) matrix: by point, then by target index. One
    # integer key per pair sorts faster than np.lexsort on two keys.
    final = np.argsort(i * m + j)
    return i[final], j[final], distances[final]

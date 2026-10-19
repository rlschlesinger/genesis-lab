"""Food resources: where food is, how it regrows, and how it is removed when eaten."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


class FoodSupply:
    """All food items in the world, stored as one ``(n, 2)`` array of x, y positions.

    Why one array instead of one ``Food`` object per item: food has no state beyond its
    position, and every tick each organism needs its distance to *all* food. With an array,
    that is a single vectorized NumPy operation instead of a Python loop over objects.

    Food has no identity beyond its row index. Indices are valid only until the next call
    that changes the supply (``spawn``, ``regrow`` or ``remove``).

    This class never creates its own random generator: the caller passes one in. That keeps
    every random draw traceable to the run's seed (see docs/decision-log.md, D-006).
    """

    def __init__(self, width: float, height: float, max_count: int, regrowth_per_tick: float):
        # The config already validates these, but FoodSupply can be built directly (in tests,
        # or later by other code), so it guards its own assumptions too.
        if width <= 0 or height <= 0:
            raise ValueError(f"bounds must be positive, got {width} x {height}")
        if max_count < 1:
            raise ValueError(f"max_count must be at least 1, got {max_count}")
        if regrowth_per_tick < 0:
            raise ValueError(f"regrowth_per_tick must be >= 0, got {regrowth_per_tick}")

        self._upper = np.array([width, height], dtype=np.float64)
        self.max_count = max_count
        self.regrowth_per_tick = regrowth_per_tick
        # Shape (0, 2): zero rows, two columns. Starting with the right shape means stacking
        # new rows onto it works the same whether the supply is empty or not.
        self._positions: FloatArray = np.empty((0, 2), dtype=np.float64)

    @property
    def count(self) -> int:
        return len(self._positions)

    @property
    def positions(self) -> FloatArray:
        """A read-only view of food positions; column 0 is x, column 1 is y.

        Read-only so that code which only *observes* food (sensors, controllers, metrics)
        cannot accidentally move or delete it. Only ``spawn`` and ``remove`` change food.
        """
        view = self._positions.view()
        view.flags.writeable = False
        return view

    def spawn(self, n: int, rng: np.random.Generator) -> int:
        """Add up to ``n`` food items at uniformly random positions, respecting ``max_count``.

        Returns the number actually added, so the caller can record the energy that
        entered the system.
        """
        if n < 0:
            raise ValueError(f"cannot spawn a negative number of items ({n})")
        k = min(n, self.max_count - self.count)
        if k == 0:
            return 0
        # low=0 for both axes; high broadcasts per column, so x is in [0, width) and y in
        # [0, height). One call draws all k points at once.
        new = rng.uniform(0.0, self._upper, size=(k, 2))
        self._positions = np.concatenate([self._positions, new])
        return k

    def regrow(self, rng: np.random.Generator) -> int:
        """Spawn one tick's worth of new food. Returns the number added.

        The count per tick is drawn from a Poisson distribution with mean
        ``regrowth_per_tick``: the standard model for "events that occur independently at
        a constant average rate". A rate of 2.0 gives 2 items per tick on average, but any
        given tick may give 0, 1, 4... (decision-log D-009).

        The Poisson draw happens even when the supply is full. That keeps the number of
        random draws per tick from depending on the state of the world.
        """
        requested = int(rng.poisson(self.regrowth_per_tick))
        return self.spawn(requested, rng)

    def remove(self, indices: ArrayLike) -> None:
        """Remove the food items at ``indices`` (eaten this tick).

        The remaining items keep their relative order, so removal is deterministic.
        Raises if an index is out of range or repeated: either would mean the caller's
        bookkeeping is wrong (for example, two organisms both "ate" the same item),
        and failing loudly beats silently miscounting energy.
        """
        idx = np.asarray(indices, dtype=np.intp)
        if idx.size == 0:
            return
        # A handful of indices per tick: plain Python checks beat NumPy's call overhead here.
        items = idx.tolist()
        if min(items) < 0 or max(items) >= self.count:
            raise IndexError(f"food index out of range for {self.count} items: {items}")
        if len(set(items)) != len(items):
            raise ValueError(f"duplicate food indices: {items}")
        # A boolean mask: True = keep. Indexing with it drops the False rows in one step.
        keep = np.ones(self.count, dtype=bool)
        keep[idx] = False
        self._positions = self._positions[keep]

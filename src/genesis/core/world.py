"""The world: a bounded 2D rectangle with hard walls, and the food inside it."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from genesis.core.config import SimulationConfig
from genesis.core.resources import FloatArray, FoodSupply


class World:
    """A ``width`` x ``height`` rectangle with its origin at the bottom-left corner.

    Positions are valid on the closed range ``[0, width] x [0, height]``. Edges are hard walls:
    anything that would move past an edge is stopped at it (decision-log D-004).
    """

    def __init__(self, width: float, height: float, food: FoodSupply):
        if width <= 0 or height <= 0:
            raise ValueError(f"bounds must be positive, got {width} x {height}")
        self.width = width
        self.height = height
        self.food = food
        self._upper = np.array([width, height], dtype=np.float64)

    @classmethod
    def from_config(
        cls,
        config: SimulationConfig,
        rng: np.random.Generator,
        kind_rng: np.random.Generator | None = None,
    ) -> World:
        """Build the starting world described by ``config``, including initial food.

        ``rng`` should be the run's *food* stream (it is wired up that way in increment 1.5),
        so initial food placement and later regrowth share one independent sequence. With two
        kinds of food (``config.resources``), ``kind_rng`` (the resources stream) decides each
        item's kind.
        """
        width, height = config.world.width, config.world.height
        kinds = None
        if config.resources is not None:
            if kind_rng is None:
                raise ValueError("two kinds of food need a generator for their kinds")
            kinds = (config.resources.share_b, kind_rng)
        food = FoodSupply(
            width, height, config.food.max_count, config.food.regrowth_per_tick, kinds
        )
        food.spawn(config.food.initial_count, rng)
        return cls(width, height, food)

    def clamp(self, positions: ArrayLike) -> FloatArray:
        """Return ``positions`` with every point pushed back inside the walls.

        Works on one point ``(x, y)`` or many ``(n, 2)``. Returns a new array and leaves the
        input untouched, so callers never have their data changed behind their back.
        """
        return np.clip(np.asarray(positions, dtype=np.float64), 0.0, self._upper)

    def contains(self, positions: ArrayLike) -> NDArray[np.bool_]:
        """True for each point inside the walls (edges included)."""
        p = np.asarray(positions, dtype=np.float64)
        return np.all((p >= 0.0) & (p <= self._upper), axis=-1)

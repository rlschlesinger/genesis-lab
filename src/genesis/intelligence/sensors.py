"""Sensing: turning world state into what each organism knows.

All organisms are sensed at once, from the same positions, before anyone moves (tick step 2).
That is the "snapshot" rule: nobody sees a world that another organism has already changed
this tick.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from genesis.core.geometry import wrap_angle

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Observations:
    """What every organism senses this tick. Each array has one entry per organism (row i is
    organism i, in the same order as the inputs to ``sense_food``).
    """

    food_found: NDArray[np.bool_]  # is any food within sense range?
    food_distance: FloatArray  # distance to nearest sensed food; inf if none
    food_bearing: FloatArray  # turn needed to face it, radians in [-pi, pi); 0 if none
    energy: FloatArray  # own current energy (unused by Milestone 1 controllers; for later)

    def __len__(self) -> int:
        return len(self.energy)


def sense_food(
    positions: FloatArray,
    headings: FloatArray,
    sense_ranges: FloatArray,
    energies: FloatArray,
    food_positions: FloatArray,
) -> Observations:
    """Find each organism's nearest food within its own sense range.

    Shapes: ``positions`` (n, 2); ``headings``, ``sense_ranges``, ``energies`` (n,);
    ``food_positions`` (m, 2).

    If two food items are exactly equally near, the one with the lower index wins. Food order
    is itself deterministic (see FoodSupply.remove), so this is reproducible.
    """
    n, m = len(positions), len(food_positions)
    found = np.zeros(n, dtype=bool)
    distance = np.full(n, np.inf)
    bearing = np.zeros(n)

    if n > 0 and m > 0:
        # Broadcasting: (n, 1, 2) - (1, m, 2) -> (n, m, 2). Row i, column j holds the vector
        # from organism i to food j. Every pair is computed in one step, with no Python loop.
        offsets = food_positions[np.newaxis, :, :] - positions[:, np.newaxis, :]
        distances = np.hypot(offsets[..., 0], offsets[..., 1])  # (n, m)

        # Food beyond an organism's own range is invisible to it: treat it as infinitely far.
        # sense_ranges[:, None] has shape (n, 1), so each row gets its own organism's range.
        distances = np.where(distances <= sense_ranges[:, np.newaxis], distances, np.inf)

        nearest = np.argmin(distances, axis=1)  # (n,) column index of the closest food
        rows = np.arange(n)
        distance = distances[rows, nearest]
        found = np.isfinite(distance)

        # Direction to the nearest food, relative to where the organism is facing.
        dx = offsets[rows, nearest, 0]
        dy = offsets[rows, nearest, 1]
        bearing = np.where(found, wrap_angle(np.arctan2(dy, dx) - headings), 0.0)

    return Observations(
        food_found=found,
        food_distance=distance,
        food_bearing=bearing,
        energy=np.asarray(energies, dtype=np.float64).copy(),
    )

"""Feeding: deciding who eats which food item this tick (part of tick step 5).

Rule (decision-log D-005, D-013):

* An organism can eat food within ``eat_radius`` of its position *after* moving.
* Each organism eats at most one item per tick; each item is eaten at most once.
* Pairs are resolved closest-first: every in-reach (organism, food) pair is sorted by
  distance, and a pair eats if neither side is already taken. So each item goes to the
  closest organism still competing for it.
* Exact distance ties are broken by a random key from the tiebreak stream, never by
  organism ID (which would favour older lineages).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.intp]


@dataclass(frozen=True, slots=True)
class Meals:
    """Matched pairs: organism ``eaters[k]`` ate food item ``foods[k]``."""

    eaters: IntArray  # row indices into the organism arrays
    foods: IntArray  # row indices into the food array

    def __len__(self) -> int:
        return len(self.eaters)


def resolve_feeding(
    organism_positions: FloatArray,
    food_positions: FloatArray,
    eat_radius: float,
    rng: np.random.Generator,
) -> Meals:
    """Match organisms to food within reach, closest pairs first."""
    empty = Meals(np.empty(0, dtype=np.intp), np.empty(0, dtype=np.intp))
    if len(organism_positions) == 0 or len(food_positions) == 0:
        return empty

    # Every organism-to-food distance at once: (n, m), the same broadcasting as sensing.
    offsets = food_positions[np.newaxis, :, :] - organism_positions[:, np.newaxis, :]
    distances = np.hypot(offsets[..., 0], offsets[..., 1])

    # np.nonzero lists the (row, column) of every True entry: the in-reach pairs only.
    org_idx, food_idx = np.nonzero(distances <= eat_radius)
    if len(org_idx) == 0:
        return empty
    pair_dist = distances[org_idx, food_idx]

    # One random key per pair. np.lexsort sorts by the *last* key first: distance, then the
    # random key for exact ties. Draws come from the dedicated tiebreak stream, so the number
    # of draws (which varies with the number of pairs) cannot shift any other subsystem.
    tiebreak = rng.random(len(org_idx))
    order = np.lexsort((tiebreak, pair_dist))

    # Greedy matching in sorted order. This is a plain Python loop: the number of in-reach
    # pairs per tick is small (usually a handful), so vectorizing it would add complexity
    # for no measurable gain. Profile before optimizing (spec section 3).
    fed: set[int] = set()
    eaten: set[int] = set()
    eaters, foods = [], []
    for k in order:
        o, f = int(org_idx[k]), int(food_idx[k])
        if o in fed or f in eaten:
            continue
        fed.add(o)
        eaten.add(f)
        eaters.append(o)
        foods.append(f)

    return Meals(np.array(eaters, dtype=np.intp), np.array(foods, dtype=np.intp))

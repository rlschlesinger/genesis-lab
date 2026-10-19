"""Reproduction: choosing who reproduces this tick, and where offspring appear (tick step 7).

Reproduction is asexual: one parent, one child. What the child inherits is decided by
``genesis.evolution.mutation`` (an exact copy when mutation is off); this module only decides
*who* reproduces and *where* the child appears.

Both functions are pure. They take a random generator (the run's *reproduction* stream) and
return results without touching organisms; the simulation applies them.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from genesis.core.world import World

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.intp]


def select_parents(eligible: NDArray[np.bool_], room: int, rng: np.random.Generator) -> IntArray:
    """Return the indices of organisms that reproduce this tick, in ascending order.

    ``eligible[i]`` says whether organism i has enough energy. If there is room for all of
    them, all reproduce. If the population cap leaves less room, the ones that get to
    reproduce are drawn uniformly at random.

    Why random and not "first in the list": the list is in ID order, so the first organisms
    are always the oldest lineages. Choosing them every time the population is at its cap
    would be a hidden advantage for founders' descendants, a selection pressure nobody chose
    (decision-log D-014).
    """
    candidates = np.flatnonzero(eligible)
    if room <= 0 or len(candidates) == 0:
        return np.empty(0, dtype=np.intp)
    if len(candidates) <= room:
        return candidates
    chosen = rng.choice(candidates, size=room, replace=False)
    # Sorted, so offspring are created (and given IDs) in a deterministic order.
    return np.sort(chosen)


def place_offspring(
    parent_positions: FloatArray, max_distance: FloatArray, world: World, rng: np.random.Generator
) -> tuple[FloatArray, FloatArray]:
    """Choose a birth position near each parent, and a random heading for each child.

    Each child appears at a random direction and distance (up to ``max_distance``, one step
    of the parent's speed) from its parent, clamped to the walls. Returns
    ``(positions (k, 2), headings (k,))``.

    The square root on the distance spreads births evenly over the disc around the parent.
    Without it, births would cluster near the centre: half of all draws would land within
    half the radius, which covers only a quarter of the area.
    """
    k = len(parent_positions)
    angle = rng.uniform(-np.pi, np.pi, size=k)
    distance = max_distance * np.sqrt(rng.uniform(0.0, 1.0, size=k))
    offsets = np.column_stack([np.cos(angle), np.sin(angle)]) * distance[:, np.newaxis]
    positions = world.clamp(parent_positions + offsets)
    headings = rng.uniform(-np.pi, np.pi, size=k)
    return positions, headings

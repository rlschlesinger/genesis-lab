"""Predation: deciding which predator catches which prey this tick (tick step 5, right after
the prey eat; D-058).

Rule:

* A predator can strike prey within ``capture_radius`` of its position, both *after* moving.
* Strikes are matched exactly as meals are (core/feeding.py): every in-reach (predator, prey)
  pair is sorted by distance, closest first, and a pair strikes if neither side is already
  taken. So each predator strikes at most once per tick, each prey is struck at most once,
  and a prey goes to the closest predator still hunting. Exact distance ties are broken by a
  random key, never by ID.
* Each strike is an *attempt*; it succeeds with probability ``capture_probability`` (one
  uniform draw per attempt, in the order the attempts were matched). A prey that escapes is
  not struck again this tick, and its predator gets nothing.

Both draws come from the predators' own ``capture`` stream, so how many strikes happen never
shifts any other subsystem's random numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from genesis.core.feeding import resolve_feeding

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.intp]


@dataclass(frozen=True, slots=True)
class Strikes:
    """This tick's attempts, and which of them caught their prey.

    ``predators[k]`` struck at ``prey[k]``; ``caught[k]`` says whether it caught it. All are
    row indices into the predator and prey arrays, in ascending predator order.
    """

    predators: IntArray
    prey: IntArray
    caught: NDArray[np.bool_]

    @property
    def attempts(self) -> int:
        return len(self.predators)

    @property
    def captures(self) -> int:
        return int(self.caught.sum())


def resolve_strikes(
    predator_positions: FloatArray,
    prey_positions: FloatArray,
    capture_radius: float,
    capture_probability: float,
    rng: np.random.Generator,
) -> Strikes:
    """Match predators to prey within reach, closest first, then decide each attempt."""
    pairs = resolve_feeding(predator_positions, prey_positions, capture_radius, rng)
    # Success is decided per attempt, in matching order (deterministic: matching is). One
    # draw per attempt even when the probability is 1, so the rule has no special case.
    caught = rng.random(len(pairs)) < capture_probability if len(pairs) else np.zeros(0, bool)
    # Reported in predator order, the order the simulation applies them in.
    order = np.argsort(pairs.eaters, kind="stable")
    return Strikes(pairs.eaters[order], pairs.foods[order], caught[order])

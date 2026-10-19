"""The sensor vector: what a neural brain is told each tick.

A brain only ever sees numbers, so everything an organism senses has to be turned into a
fixed list of numbers, the same meaning in the same position every tick. That list is the
*input vector*. Getting it right matters more than the network itself: a brain cannot react
to something it isn't told, and an input on a wildly different scale from the others (say
energy in the hundreds next to directions between -1 and 1) would drown them out until
evolution happened to shrink its weights. So every input is *normalised*: designed to lie in
[-1, 1], with 0 meaning "nothing to report".

The seven inputs (D-040), in order:

====  ================  ==========================================================  ========
 #    name              meaning                                                     range
====  ================  ==========================================================  ========
 0    food_seen         1 if any food is within sense range, else 0                 0 or 1
 1    food_ahead        cos(bearing to food): 1 straight ahead, -1 straight behind  [-1, 1]
 2    food_left         sin(bearing to food): 1 to the left, -1 to the right        [-1, 1]
 3    food_closeness    1 - distance / sense range: 1 touching it, 0 at the edge    [0, 1]
 4    energy            energy / reproduction threshold, capped at 1                [0, 1]
 5    wall_ahead        1 - distance to the wall straight ahead / sense range;      [0, 1]
                        0 when the wall is out of sight
 6    noise             a fresh random number each tick (controller stream)         [-1, 1]
====  ================  ==========================================================  ========

Inputs 1-3 are 0 when no food is in sight; input 0 is how the brain tells "no food" apart
from "food exactly sideways" (where cos is also 0).

Why cos and sin instead of the angle itself: the bearing jumps from +pi to -pi as food passes
directly behind, so two almost identical situations would get opposite inputs. (cos, sin)
changes smoothly all the way round.

Why the wall sensor: the world has hard walls (D-004). The food seeker never needed to know,
because it turns toward food; a brain that wants to avoid pressing against a wall needs to
see it. Distances are measured along the heading, in the same units and against the same
sense range as food, so "close" means the same thing for both.

Why noise: the baseline controllers wander randomly when they see nothing. Without a source
of randomness a brain could only go straight or circle, an unfair handicap in the
comparison (E007). The brain decides how much the noise matters through its weights,
including not at all.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from genesis.intelligence.neural import N_INPUTS
from genesis.intelligence.sensors import Observations

FloatArray = NDArray[np.float64]

INPUT_NAMES: tuple[str, ...] = (
    "food_seen",
    "food_ahead",
    "food_left",
    "food_closeness",
    "energy",
    "wall_ahead",
    "noise",
)
assert len(INPUT_NAMES) == N_INPUTS  # the brain and its senses must agree on the count


def wall_distance_ahead(
    positions: FloatArray, headings: FloatArray, width: float, height: float
) -> FloatArray:
    """How far each organism could travel straight ahead before reaching a wall.

    The world is the rectangle [0, width] x [0, height]. Moving along heading h, x changes by
    cos(h) per unit travelled and y by sin(h). The ray reaches a vertical wall after
    (width - x) / cos(h) units if moving right, or x / -cos(h) if moving left; likewise for
    the horizontal walls with sin(h). Whichever wall comes first is the answer. A direction
    that never reaches a pair of walls (cos(h) exactly 0) gives infinity for that pair.
    """
    positions = np.asarray(positions, dtype=np.float64).reshape(-1, 2)
    headings = np.asarray(headings, dtype=np.float64)
    if len(positions) == 0:
        return np.empty(0)
    dx, dy = np.cos(headings), np.sin(headings)
    to_x_wall = np.where(dx > 0, width - positions[:, 0], positions[:, 0])
    to_y_wall = np.where(dy > 0, height - positions[:, 1], positions[:, 1])
    # np.divide with where= skips the division where the direction component is 0, leaving
    # the inf from `out` there, so no divide-by-zero warning is raised. A component that is
    # tiny but not 0 (hypothesis found sin(h) ~ 1e-308) overflows to inf, which is also the
    # right answer: that wall is never reached. Hence over="ignore".
    with np.errstate(over="ignore"):
        along_x = np.divide(to_x_wall, np.abs(dx), out=np.full_like(dx, np.inf), where=dx != 0)
        along_y = np.divide(to_y_wall, np.abs(dy), out=np.full_like(dy, np.inf), where=dy != 0)
    # Positions are clamped inside the world, so distances are never negative; max() guards
    # against a position a rounding step outside a wall.
    return np.maximum(np.minimum(along_x, along_y), 0.0)


def brain_inputs(
    obs: Observations,
    sense_ranges: FloatArray,
    reproduction_thresholds: FloatArray,
    wall_distances: FloatArray,
    noise: FloatArray,
) -> FloatArray:
    """The (n, 7) input matrix: row k is organism k's input vector, columns as INPUT_NAMES.

    ``sense_ranges`` and ``reproduction_thresholds`` are each organism's own traits (an
    organism knows how far it can see and how full it is); ``wall_distances`` comes from
    ``wall_distance_ahead``; ``noise`` must already lie in [-1, 1].
    """
    n = len(obs)
    sense_ranges = np.asarray(sense_ranges, dtype=np.float64)
    thresholds = np.asarray(reproduction_thresholds, dtype=np.float64)
    wall_distances = np.asarray(wall_distances, dtype=np.float64)
    noise = np.asarray(noise, dtype=np.float64)
    for name, array in [
        ("sense_ranges", sense_ranges),
        ("reproduction_thresholds", thresholds),
        ("wall_distances", wall_distances),
        ("noise", noise),
    ]:
        if array.shape != (n,):
            raise ValueError(f"{name} must have shape ({n},), got {array.shape}")
    if np.any(sense_ranges <= 0) or np.any(thresholds <= 0):
        raise ValueError("sense ranges and reproduction thresholds must be positive")
    if np.any(~(np.abs(noise) <= 1.0)):  # also catches NaN
        raise ValueError("noise must lie in [-1, 1]")

    seen = obs.food_found
    inputs = np.zeros((n, N_INPUTS))
    inputs[:, 0] = seen
    # Unseen food has bearing 0 and distance inf; np.where keeps those columns at exactly 0.
    inputs[:, 1] = np.where(seen, np.cos(obs.food_bearing), 0.0)
    inputs[:, 2] = np.where(seen, np.sin(obs.food_bearing), 0.0)
    with np.errstate(invalid="ignore"):  # inf / range for unseen food; masked out by where
        closeness = 1.0 - obs.food_distance / sense_ranges
    # Sensed food is within range by definition, so closeness is in [0, 1]; the clip only
    # absorbs rounding at exactly the edge of range.
    inputs[:, 3] = np.where(seen, np.clip(closeness, 0.0, 1.0), 0.0)
    inputs[:, 4] = np.clip(obs.energy / thresholds, 0.0, 1.0)
    inputs[:, 5] = np.clip(1.0 - wall_distances / sense_ranges, 0.0, 1.0)
    inputs[:, 6] = noise
    return inputs

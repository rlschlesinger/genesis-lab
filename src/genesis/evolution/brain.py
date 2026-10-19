"""Brains as genes: founders' random weights, and mutation at birth.

A brain's 62 weights and biases (``Brain.to_vector()``) are inherited exactly like the scalar
genes in genome.py: a child gets its parent's brain, and at each birth a few weights change by
a small random step. Nothing else ever changes a weight. There is no learning within a
lifetime, so any improvement in behaviour over a run comes from which brains reproduce.

Founders are different from scalar genes in one way (D-041): each founder gets its *own*
random brain, while all founders share one scalar genome. A brain with identical random
weights everywhere would give selection nothing to choose between until mutation had built up
variation, and a brain of all zeros would make every founder behave identically (turn 0,
throttle 0.5). Random weights mean the founding population already contains many different
behaviours, most of them useless, for selection to act on from the first generation.

All randomness here comes from the ``brain`` stream, the seventh stream, added at the end
(D-012), so runs without brains draw exactly the same numbers as before.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from genesis.core.config import BrainConfig
from genesis.intelligence.neural import PARAMETER_COUNT, Brain

FloatArray = NDArray[np.float64]


def reflect_array(values: FloatArray, low: float, high: float) -> FloatArray:
    """``mutation.reflect`` for a whole array: fold values back into [low, high].

    Same rule and same reason as for genes (D-019): clamping would pile weights up exactly on
    the limit, which would look like selection for extreme weights.
    """
    width = high - low
    t = np.mod(np.asarray(values, dtype=np.float64) - low, 2 * width)
    return low + np.where(t > width, 2 * width - t, t)


def founder_brains(n: int, config: BrainConfig, rng: np.random.Generator) -> list[Brain]:
    """One independent random brain per founder, drawn in founder (ID) order.

    Every weight is Normal(0, initial_sd), reflected into [-weight_limit, weight_limit]. One
    vectorized draw of shape (n, 62) consumes the stream identically to n draws of 62.
    """
    limit = config.weight_limit
    draws = rng.normal(0.0, config.initial_sd, size=(n, PARAMETER_COUNT))
    return [Brain.from_vector(row) for row in reflect_array(draws, -limit, limit)]


def mutate_brain(brain: Brain, config: BrainConfig, rng: np.random.Generator) -> tuple[Brain, int]:
    """A child's brain and how many of its weights changed.

    Per weight: a uniform draw decides whether it mutates (probability ``mutation_rate``);
    a normal draw gives the step, Normal(0, mutation_size); the result is reflected into
    the limits. Both draws happen for all 62 weights at every birth, whether or not anything
    mutates, so the stream advances by the same amount per birth (the rule of D-009 and
    mutation.py).

    The parent's brain is never changed (its arrays are read-only). With no change the
    parent's own Brain object is returned: sharing it is safe because nothing can modify it.
    """
    limit = config.weight_limit
    hits = rng.random(PARAMETER_COUNT) < config.mutation_rate
    steps = rng.normal(0.0, config.mutation_size, size=PARAMETER_COUNT)
    before = brain.to_vector()
    after = np.where(hits, reflect_array(before + steps, -limit, limit), before)
    changed = int(np.count_nonzero(after != before))
    if changed == 0:
        return brain, 0
    return Brain.from_vector(after, brain.shape), changed

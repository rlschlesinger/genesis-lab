"""Significance tests, written out by hand so every step is visible (SciPy arrives in M3).

All tests answer: *if there were really no difference (the null hypothesis), how often would
chance alone give a result at least this extreme?* That probability is the p-value. A small
p-value makes "no difference" hard to believe; it is NOT the probability a hypothesis is true.

Unit of analysis: one run. Pass one number per run (or per pair of runs), never per organism
(docs/experiment-design.md).

    sign_test                 direction only: is one side ahead more often than a coin flip?
    paired_permutation_test   paired differences: flip signs at random, compare the means
    permutation_test          two independent groups: shuffle the labels, compare the means
    holm                      adjust p-values when several hypotheses are tested together
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

EXACT_LIMIT = 2**16  # enumerate every arrangement when there are at most this many


@dataclass(frozen=True, slots=True)
class SignTestResult:
    positive: int
    negative: int
    ties: int  # exact zeros carry no direction, so they are left out
    p_value: float  # two-sided, exact


@dataclass(frozen=True, slots=True)
class PermutationResult:
    observed: float  # the statistic for the real data (a mean or a difference of means)
    p_value: float  # two-sided
    exact: bool  # True: every arrangement checked; False: a random sample of them
    arrangements: int  # how many arrangements were evaluated


def sign_test(differences: Sequence[float]) -> SignTestResult:
    """Exact two-sided sign test.

    Under the null, each non-zero difference is positive with probability 1/2, so the number
    of positives follows a Binomial(n, 1/2) distribution. The p-value is the probability of a
    split at least as lopsided as the one observed, in either direction.

    Example: 10 of 10 positive -> 2 x (1/2)^10 = 0.00195.
    """
    positive = sum(d > 0 for d in differences)
    negative = sum(d < 0 for d in differences)
    ties = len(differences) - positive - negative
    n = positive + negative
    if n == 0:
        return SignTestResult(positive, negative, ties, 1.0)
    k = min(positive, negative)
    # P(X <= k) for X ~ Binomial(n, 1/2): count the ways to get k or fewer, out of 2^n.
    one_tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return SignTestResult(positive, negative, ties, min(1.0, 2 * one_tail))


def paired_permutation_test(
    differences: Sequence[float],
    rng: np.random.Generator | None = None,
    n_samples: int = 10_000,
    exact: bool | None = None,
) -> PermutationResult:
    """Two-sided paired permutation (sign-flip) test on the mean difference.

    Under the null, the label "condition A minus condition B" could just as well have been
    "B minus A" for each pair, so each difference's sign is arbitrary. Flipping signs in every
    possible way gives the distribution of means chance alone produces. The p-value is the
    fraction of those means at least as far from zero as the real one.

    With n pairs there are 2**n sign patterns. Up to EXACT_LIMIT they are all checked (an
    exact p-value). Beyond that, ``n_samples`` random patterns are drawn from ``rng`` (which
    must be given, so results are reproducible), and the p-value uses the "+1" correction:
    (hits + 1) / (samples + 1). The real data is itself one valid arrangement, and the
    correction stops a sampled test from ever reporting p = 0.

    ``exact``: None chooses automatically; True/False forces one method (mainly for testing
    that the two agree).
    """
    d = np.asarray(differences, dtype=np.float64)
    n = len(d)
    observed = float(d.mean()) if n else 0.0
    if n == 0 or np.all(d == 0):
        return PermutationResult(observed, 1.0, True, 1)
    threshold = abs(observed) * (1 - 1e-12)  # tolerate rounding in "at least as extreme"

    use_exact = (2**n <= EXACT_LIMIT) if exact is None else exact
    if use_exact:
        signs = np.array(list(itertools.product((1.0, -1.0), repeat=n)))  # (2**n, n)
        means = signs @ d / n
        hits = int(np.sum(np.abs(means) >= threshold))
        return PermutationResult(observed, hits / len(signs), True, len(signs))

    if rng is None:
        raise ValueError("a seeded rng is required when the test has to sample arrangements")
    signs = rng.choice((-1.0, 1.0), size=(n_samples, n))
    means = signs @ d / n
    hits = int(np.sum(np.abs(means) >= threshold))
    return PermutationResult(observed, (hits + 1) / (n_samples + 1), False, n_samples)


def permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    rng: np.random.Generator | None = None,
    n_samples: int = 10_000,
    exact: bool | None = None,
) -> PermutationResult:
    """Two-sided permutation test on mean(a) - mean(b), for two *independent* groups.

    Under the null, the group labels are arbitrary: any way of splitting the pooled values into
    groups of the same sizes was equally likely. The p-value is the fraction of splits whose
    difference in means is at least as large (in size) as the real one. Exact when there are
    at most EXACT_LIMIT splits; otherwise sampled as in ``paired_permutation_test``.
    """
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    pooled = np.concatenate([x, y])
    n_a, total = len(x), len(pooled)
    observed = float(x.mean() - y.mean())
    threshold = abs(observed) * (1 - 1e-12)
    if np.all(pooled == pooled[0]):
        return PermutationResult(observed, 1.0, True, 1)

    def diff(in_a: np.ndarray) -> float:
        return float(pooled[in_a].mean() - pooled[~in_a].mean())

    splits = math.comb(total, n_a)
    use_exact = (splits <= EXACT_LIMIT) if exact is None else exact
    if use_exact:
        hits = 0
        for chosen in itertools.combinations(range(total), n_a):
            mask = np.zeros(total, dtype=bool)
            mask[list(chosen)] = True
            hits += abs(diff(mask)) >= threshold
        return PermutationResult(observed, hits / splits, True, splits)

    if rng is None:
        raise ValueError("a seeded rng is required when the test has to sample arrangements")
    hits = 0
    for _ in range(n_samples):
        mask = np.zeros(total, dtype=bool)
        mask[rng.choice(total, size=n_a, replace=False)] = True
        hits += abs(diff(mask)) >= threshold
    return PermutationResult(observed, (hits + 1) / (n_samples + 1), False, n_samples)


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values for testing several hypotheses together.

    Testing k hypotheses at the 5% level gives each one a 5% chance of a false alarm, so the
    chance of at least one is much higher (about 23% for k = 5). Holm's method controls that
    overall chance: sort the p-values from smallest, multiply the i-th smallest (counting from
    0) by (k - i), and make the results non-decreasing in that order. Compare each adjusted
    value with 0.05 as usual. Returned in the same order as the input.
    """
    k = len(p_values)
    order = sorted(range(k), key=lambda i: p_values[i])
    adjusted = [0.0] * k
    running_max = 0.0
    for rank, i in enumerate(order):
        running_max = max(running_max, min(1.0, (k - rank) * p_values[i]))
        adjusted[i] = running_max
    return adjusted

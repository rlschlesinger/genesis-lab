"""Our hand-written tests (2.7) against SciPy's implementations of the same tests.

Where both compute an exact answer, they must agree to rounding. Agreement from two
independent implementations is strong evidence both are right.
"""

import numpy as np
import pytest
from scipy import stats

from genesis.analytics.significance import paired_permutation_test, permutation_test, sign_test


@pytest.mark.parametrize(("k", "n"), [(k, n) for n in (1, 5, 10, 20) for k in range(n + 1)])
def test_sign_test_equals_scipy_binomial_test(k, n):
    differences = [1.0] * k + [-1.0] * (n - k)
    assert sign_test(differences).p_value == pytest.approx(stats.binomtest(k, n).pvalue, abs=1e-12)


@pytest.mark.parametrize("seed", range(10))
def test_exact_paired_permutation_equals_scipy(seed):
    rng = np.random.default_rng(seed)
    x, y = rng.normal(0.3, 1, 10), rng.normal(0, 1, 10)
    ours = paired_permutation_test(x - y)
    ref = stats.permutation_test(
        (x, y),
        lambda a, b, axis: np.mean(a - b, axis=axis),
        permutation_type="samples",
        n_resamples=np.inf,
        alternative="two-sided",
    )
    assert ours.exact and ours.p_value == pytest.approx(ref.pvalue, abs=1e-12)


@pytest.mark.parametrize("seed", range(6))
def test_exact_two_group_permutation_equals_scipy_for_equal_groups(seed):
    rng = np.random.default_rng(seed)
    a, b = rng.normal(0.5, 1, 6), rng.normal(0, 1, 6)
    ours = permutation_test(a, b)
    ref = stats.permutation_test(
        (a, b),
        lambda u, v, axis: np.mean(u, axis=axis) - np.mean(v, axis=axis),
        permutation_type="independent",
        n_resamples=np.inf,
        alternative="two-sided",
    )
    assert ours.exact and ours.p_value == pytest.approx(ref.pvalue, abs=1e-12)


def test_two_sided_definitions_differ_when_the_null_is_asymmetric():
    # Ours counts arrangements with |difference| >= |observed|. SciPy doubles the smaller
    # one-sided p-value. With equal group sizes the null distribution is symmetric and the
    # two agree (tests above); with unequal sizes it needn't be, so they can differ. Both
    # are legitimate; what matters is stating which one is used.
    a, b = [0.0, 0.0, 0.0, 9.0], [1.0, 2.0]
    ours = permutation_test(a, b).p_value
    ref = stats.permutation_test(
        (a, b),
        lambda u, v, axis: np.mean(u, axis=axis) - np.mean(v, axis=axis),
        permutation_type="independent",
        n_resamples=np.inf,
    ).pvalue
    assert ours != pytest.approx(ref)

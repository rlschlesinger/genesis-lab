"""Tests for the significance tests, against answers worked out by hand."""

import math

import numpy as np
import pytest

from genesis.analytics.significance import (
    holm,
    paired_permutation_test,
    permutation_test,
    sign_test,
)

# --- Sign test ----------------------------------------------------------------------------


def test_sign_test_ten_of_ten():
    result = sign_test([1.0] * 10)
    assert (result.positive, result.negative) == (10, 0)
    assert result.p_value == 2 / 2**10  # exactly 0.001953125


def test_sign_test_nine_of_ten():
    # P(X <= 1) for Binomial(10, 1/2) = (1 + 10) / 1024; two-sided doubles it.
    assert sign_test([1.0] * 9 + [-1.0]).p_value == 2 * 11 / 1024


def test_sign_test_even_split_is_unremarkable():
    assert sign_test([1, -1] * 5).p_value == 1.0


def test_sign_test_ignores_ties():
    result = sign_test([1.0] * 9 + [0.0])  # the tie from E001's lineages_end
    assert result.ties == 1
    assert result.p_value == 2 / 2**9


def test_sign_test_direction_only():
    # Sizes don't matter: tiny or huge, 10 of 10 is the same evidence.
    assert sign_test([0.001] * 10).p_value == sign_test([1000.0] * 10).p_value


def test_sign_test_edge_cases():
    assert sign_test([]).p_value == 1.0
    assert sign_test([0.0, 0.0]).p_value == 1.0
    assert sign_test([5.0]).p_value == 1.0  # one coin flip can't be surprising


# --- Paired permutation test --------------------------------------------------------------


def test_paired_exact_small_case_by_hand():
    # [1, 2, 3]: 8 sign patterns. Only +++ and --- reach |mean| = 2, so p = 2/8.
    result = paired_permutation_test([1.0, 2.0, 3.0])
    assert result.exact and result.arrangements == 8
    assert result.observed == 2.0
    assert result.p_value == 0.25


def test_paired_all_positive_matches_the_extreme_tail():
    # Ten equal positive differences: only the two all-same-sign patterns are as extreme.
    assert paired_permutation_test([3.0] * 10).p_value == 2 / 1024


def test_paired_uses_sizes_unlike_the_sign_test():
    # 9 small positives and 1 huge negative: the sign test is impressed, the mean isn't.
    diffs = [1.0] * 9 + [-50.0]
    assert sign_test(diffs).p_value < 0.05
    assert paired_permutation_test(diffs).p_value > 0.5


def test_paired_zero_differences():
    assert paired_permutation_test([0.0, 0.0, 0.0]).p_value == 1.0


def test_paired_sampled_agrees_with_exact():
    rng = np.random.default_rng(0)
    diffs = rng.normal(0.4, 1.0, size=14)  # 2**14 = 16,384 patterns: exact is feasible
    exact = paired_permutation_test(diffs)
    sampled = paired_permutation_test(
        diffs, rng=np.random.default_rng(1), n_samples=20_000, exact=False
    )
    assert exact.exact and not sampled.exact
    assert sampled.p_value == pytest.approx(exact.p_value, abs=0.01)


def test_paired_sampling_requires_a_seeded_rng():
    with pytest.raises(ValueError, match="seeded rng"):
        paired_permutation_test(np.ones(20))


def test_paired_sampled_is_reproducible_with_a_seed():
    diffs = np.linspace(-1, 2, 20)
    a = paired_permutation_test(diffs, rng=np.random.default_rng(5))
    b = paired_permutation_test(diffs, rng=np.random.default_rng(5))
    assert a == b


def test_false_alarm_rate_is_at_most_five_percent_when_nothing_is_going_on():
    # Calibration: generate 400 datasets where the null is TRUE (symmetric noise around 0).
    # A correct test calls "p < 0.05" in at most about 5% of them.
    rng = np.random.default_rng(42)
    p_values = [paired_permutation_test(rng.normal(0, 1, size=10)).p_value for _ in range(400)]
    false_alarms = np.mean(np.array(p_values) < 0.05)
    assert 0.02 < false_alarms < 0.08


def test_detects_a_real_difference():
    rng = np.random.default_rng(3)
    p_values = [paired_permutation_test(rng.normal(1.0, 1, size=10)).p_value for _ in range(200)]
    assert np.mean(np.array(p_values) < 0.05) > 0.7  # usually finds a 1-sd effect with 10 pairs


# --- Two-group permutation test -----------------------------------------------------------


def test_two_groups_completely_separated():
    # 5 vs 5, every value in a above every value in b: of C(10,5) = 252 splits, only the real
    # one and its mirror image are as extreme.
    result = permutation_test([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    assert result.exact and result.arrangements == 252
    assert result.p_value == pytest.approx(2 / 252)


def test_two_groups_identical_values():
    assert permutation_test([2.0, 2.0], [2.0, 2.0]).p_value == 1.0


def test_two_groups_overlapping_is_unremarkable():
    assert permutation_test([1, 3, 5, 7], [2, 4, 6, 8]).p_value > 0.5


def test_two_groups_sampled_when_large():
    rng = np.random.default_rng(0)
    a, b = rng.normal(0, 1, 15), rng.normal(0, 1, 15)  # C(30,15) ~ 155 million splits
    result = permutation_test(a, b, rng=np.random.default_rng(1), n_samples=2000)
    assert not result.exact and result.arrangements == 2000
    assert 0 < result.p_value <= 1


# --- Holm correction ----------------------------------------------------------------------


def test_holm_worked_example():
    # Sorted p: 0.01, 0.02, 0.03, 0.04 -> x4, x3, x2, x1 = 0.04, 0.06, 0.06, 0.04
    # -> made non-decreasing: 0.04, 0.06, 0.06, 0.06. Returned in input order.
    assert holm([0.03, 0.01, 0.04, 0.02]) == pytest.approx([0.06, 0.04, 0.06, 0.06])


def test_holm_never_lowers_a_p_value_and_caps_at_one():
    raw = [0.5, 0.001, 0.2, 0.9]
    adjusted = holm(raw)
    assert all(adj >= p for adj, p in zip(adjusted, raw, strict=True))
    assert max(adjusted) <= 1.0


def test_holm_single_test_unchanged():
    assert holm([0.03]) == [0.03]


def test_why_correction_matters():
    # With 5 independent tests at 5%, P(at least one false alarm) = 1 - 0.95^5 ~ 23%.
    chance_of_any_false_alarm = 1 - 0.95**5
    assert chance_of_any_false_alarm == pytest.approx(0.226, abs=0.001)
    assert math.isclose(holm([0.04] * 5)[0], 0.2)  # five borderline results: none survive

"""Tests for angle wrapping."""

import numpy as np
import pytest

from genesis.core.geometry import wrap_angle


@pytest.mark.parametrize(
    ("angle", "expected"),
    [
        (0.0, 0.0),
        (1.0, 1.0),  # already in range: unchanged
        (-1.0, -1.0),
        (3 * np.pi / 2, -np.pi / 2),  # three-quarter turn left == quarter turn right
        (2 * np.pi, 0.0),  # a full turn is no turn
        (np.pi, -np.pi),  # the boundary maps to -pi: range is [-pi, pi)
        (-5 * np.pi / 2, -np.pi / 2),
    ],
)
def test_wrap_angle(angle, expected):
    assert wrap_angle(angle) == pytest.approx(expected)


def test_wrap_angle_works_on_arrays():
    result = wrap_angle([0.0, 2 * np.pi, 3 * np.pi])
    np.testing.assert_allclose(result, [0.0, 0.0, -np.pi], atol=1e-12)


def test_wrapped_angles_stay_in_range_and_point_the_same_way():
    # Many angles over several turns: every result lands in [-pi, pi), and each still points
    # in its original direction (same cosine and sine).
    angles = np.linspace(-20.0, 20.0, 4001)
    wrapped = wrap_angle(angles)
    assert np.all((wrapped >= -np.pi) & (wrapped < np.pi))
    np.testing.assert_allclose(np.cos(wrapped), np.cos(angles), atol=1e-12)
    np.testing.assert_allclose(np.sin(wrapped), np.sin(angles), atol=1e-12)

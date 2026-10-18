"""Small geometry helpers shared by sensing and movement."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def wrap_angle(angle: ArrayLike) -> NDArray[np.float64]:
    """Map any angle (radians) into ``[-pi, pi)``.

    Angles that differ by a full turn (2*pi) point the same way, so 3*pi/2 and -pi/2 are the
    same direction. Wrapping gives each direction a single representation. It matters for
    bearings: "turn -pi/2" (a quarter turn right) is what we want, not "turn 3*pi/2".
    """
    return (np.asarray(angle, dtype=np.float64) + np.pi) % (2 * np.pi) - np.pi

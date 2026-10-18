"""Movement: applying actions to positions and headings (tick step 4).

Order within a move: first turn, then step forward along the new heading, then clamp to the
walls. Turning first means an organism can react to food it sensed this tick.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from genesis.core.geometry import wrap_angle
from genesis.core.world import World
from genesis.intelligence.controllers import Actions

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class MoveResult:
    positions: FloatArray  # (n, 2) after clamping to the walls
    headings: FloatArray  # (n,) wrapped to [-pi, pi)
    distances: FloatArray  # (n,) distance actually travelled; movement cost is charged on this


def move(
    positions: FloatArray,
    headings: FloatArray,
    actions: Actions,
    speeds: FloatArray,
    max_turns: FloatArray,
    world: World,
) -> MoveResult:
    """Apply each organism's requested turn and throttle, within its physical limits.

    Returns new arrays; the inputs are not modified.
    """
    # A controller producing NaN (for example, a neural network with a numerical fault) would
    # silently turn positions into NaN and corrupt the run. Fail here, at the source.
    if not (np.isfinite(actions.turn).all() and np.isfinite(actions.throttle).all()):
        raise ValueError("controller produced non-finite actions (NaN or inf)")

    # Physical limits: the controller asks, the body decides.
    turn = np.clip(actions.turn, -max_turns, max_turns)
    throttle = np.clip(actions.throttle, 0.0, 1.0)

    new_headings = wrap_angle(headings + turn)
    step = throttle * speeds
    # Heading -> direction: cos gives the x share of the step, sin the y share.
    direction = np.column_stack([np.cos(new_headings), np.sin(new_headings)])
    target = positions + step[:, np.newaxis] * direction
    new_positions = world.clamp(target)

    # Measured after clamping: an organism pushing against a wall moves less, so it pays less.
    moved = new_positions - positions
    distances = np.hypot(moved[:, 0], moved[:, 1])
    return MoveResult(positions=new_positions, headings=new_headings, distances=distances)

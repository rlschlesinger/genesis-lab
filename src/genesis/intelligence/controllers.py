"""Controllers: the decision step. Observations in, actions out.

A controller is a *pure* decision function: it reads observations and returns actions, and
never changes the world. The simulation applies the actions afterwards. This boundary is what
lets a neural network replace these hand-written rules in Milestone 4 without touching any
other code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from genesis.intelligence.sensors import Observations

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Actions:
    """What every organism wants to do this tick (one entry per organism).

    These are *requests*. Movement enforces each organism's physical limits, so a controller
    cannot exceed its traits even if it asks to.
    """

    turn: FloatArray  # desired heading change, radians; clipped to +/- max_turn
    throttle: FloatArray  # 0 = stay still, 1 = full speed; clipped to [0, 1]


class Controller(Protocol):
    """Anything with this ``decide`` method counts as a controller.

    A Protocol defines an interface by shape: classes don't need to inherit from it, they only
    need a matching method. Type checkers verify the match.
    """

    def decide(self, obs: Observations, rng: np.random.Generator) -> Actions: ...


@dataclass(frozen=True, slots=True)
class RandomWalk:
    """Baseline: wander with small random turns, at full speed, ignoring food entirely.

    Turns are drawn from a normal distribution centred on 0 (usually small, occasionally
    large). A uniform draw over every possible angle would mostly be cut off at max_turn by
    movement, giving jerky zig-zags instead of wandering.
    """

    turn_sd: float = 0.3  # standard deviation of each random turn, radians

    def decide(self, obs: Observations, rng: np.random.Generator) -> Actions:
        n = len(obs)
        return Actions(turn=rng.normal(0.0, self.turn_sd, size=n), throttle=np.ones(n))


@dataclass(frozen=True, slots=True)
class NearestFoodSeeker:
    """Baseline: turn toward the nearest sensed food; otherwise behave exactly like RandomWalk.

    Matching RandomWalk whenever no food is in range, and always moving at full speed, is
    deliberate. The *only* difference between the two controllers is the response to sensed
    food, so any difference in outcomes can be attributed to that response.
    """

    turn_sd: float = 0.3

    def decide(self, obs: Observations, rng: np.random.Generator) -> Actions:
        n = len(obs)
        # Draw random turns for *every* organism, even those that will use the bearing
        # instead. That keeps the number of random draws independent of how many organisms
        # see food, the same reasoning as FoodSupply.regrow (decision-log D-009).
        wander = rng.normal(0.0, self.turn_sd, size=n)
        # Ask to turn the full bearing; movement limits it to max_turn, so an organism facing
        # away from food turns toward it over several ticks.
        turn = np.where(obs.food_found, obs.food_bearing, wander)
        return Actions(turn=turn, throttle=np.ones(n))


CONTROLLERS: dict[str, type[RandomWalk] | type[NearestFoodSeeker]] = {
    "random_walk": RandomWalk,
    "nearest_food_seeker": NearestFoodSeeker,
}


def make_controller(name: str) -> Controller:
    """Build a controller from its config name (``organisms.controller``)."""
    try:
        return CONTROLLERS[name]()
    except KeyError:
        raise ValueError(
            f"unknown controller {name!r}; choose from {sorted(CONTROLLERS)}"
        ) from None

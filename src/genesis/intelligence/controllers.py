"""Controllers: the decision step. Observations in, actions out.

A controller is a *pure* decision function: it reads observations and returns actions, and
never changes the world. The simulation applies the actions afterwards. This boundary is what
lets a neural network replace these hand-written rules in Milestone 4 without touching any
other code: ``NeuralController`` below is one more controller, chosen by config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from genesis.core.geometry import wrap_angle
from genesis.intelligence.brain_inputs import brain_inputs
from genesis.intelligence.neural import Activations, BrainStack, forward
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

    def decide(
        self, obs: Observations, rng: np.random.Generator, brains: BrainStack | None = None
    ) -> Actions: ...


@dataclass(frozen=True, slots=True)
class RandomWalk:
    """Baseline: wander with small random turns, at full speed, ignoring food entirely.

    Turns are drawn from a normal distribution centred on 0 (usually small, occasionally
    large). A uniform draw over every possible angle would mostly be cut off at max_turn by
    movement, giving jerky zig-zags instead of wandering.
    """

    turn_sd: float = 0.3  # standard deviation of each random turn, radians

    def decide(
        self, obs: Observations, rng: np.random.Generator, brains: BrainStack | None = None
    ) -> Actions:
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

    def decide(
        self, obs: Observations, rng: np.random.Generator, brains: BrainStack | None = None
    ) -> Actions:
        n = len(obs)
        # Draw random turns for *every* organism, even those that will use the bearing
        # instead. That keeps the number of random draws independent of how many organisms
        # see food, the same reasoning as FoodSupply.regrow (decision-log D-009).
        wander = rng.normal(0.0, self.turn_sd, size=n)
        # Ask to turn the full bearing; movement limits it to max_turn, so an organism facing
        # away from food turns toward it over several ticks.
        turn = np.where(obs.food_found, obs.food_bearing, wander)
        return Actions(turn=turn, throttle=np.ones(n))


@dataclass(frozen=True, slots=True)
class FleeSeeker:
    """Designed evasion (E008, D-062): turn straight away from the nearest predator in sight;
    otherwise behave exactly like NearestFoodSeeker.

    The hand-written counterpart to evolved avoidance. It reads ``obs.threat`` (the nearest
    predator within sense range, the same sensing neural prey get, D-059) and asks to turn by
    bearing + pi, so it faces directly away; movement limits the turn to max_turn per tick,
    so it swings round over several ticks. Full speed always, like the seeker. Its random
    draws are the seeker's, every tick, so with no predator in sight it is the seeker, draw
    for draw. Without a ``threat`` (a world without predators) it simply is the seeker.
    """

    turn_sd: float = 0.3

    def decide(
        self, obs: Observations, rng: np.random.Generator, brains: BrainStack | None = None
    ) -> Actions:
        seeking = NearestFoodSeeker(self.turn_sd).decide(obs, rng)
        if obs.threat is None:
            return seeking
        away = wrap_angle(obs.threat.bearing + np.pi)
        return Actions(
            turn=np.where(obs.threat.found, away, seeking.turn), throttle=seeking.throttle
        )


@dataclass(frozen=True, slots=True)
class Thought:
    """One tick of neural decision-making, kept whole so it can be inspected (4.6)."""

    inputs: FloatArray  # (n, 7) or (n, 10) as built by brain_inputs, before clipping
    activations: Activations  # every intermediate value of the forward pass
    actions: Actions


@dataclass(frozen=True, slots=True)
class NeuralController:
    """Each organism's own evolved brain decides (Milestone 4, D-042).

    Per tick: draw one noise value per organism from the controller stream, build the
    7-input matrix (brain_inputs), run every brain in one forward pass, and map the two
    outputs to actions:

    - turn = output 0 (in (-1, 1)) x the organism's own max_turn: the brain chooses a
      fraction of what its body allows, so a turn output never saturates against the limit.
    - throttle = output 1, already in (0, 1).

    Like the rule-based controllers it is pure: same observations, brains and random state
    give the same actions, and nothing in the world is touched.
    """

    def think(self, obs: Observations, rng: np.random.Generator, brains: BrainStack) -> Thought:
        n = len(obs)
        if obs.body is None:
            raise ValueError("the neural controller needs Observations.body (BodySenses)")
        if len(brains) != n:
            raise ValueError(f"{len(brains)} brains for {n} organisms")
        # One draw per organism every tick, whatever the brains do with it (D-009's rule).
        noise = rng.uniform(-1.0, 1.0, size=n)
        body = obs.body
        inputs = brain_inputs(
            obs, body.sense_range, body.reproduction_threshold, body.wall_distance, noise
        )
        activations = forward(brains, inputs)
        actions = Actions(
            turn=activations.outputs[:, 0] * body.max_turn,
            throttle=activations.outputs[:, 1].copy(),
        )
        return Thought(inputs, activations, actions)

    def decide(
        self, obs: Observations, rng: np.random.Generator, brains: BrainStack | None = None
    ) -> Actions:
        if len(obs) == 0:  # an extinct population: nothing to decide, nothing drawn
            return Actions(turn=np.empty(0), throttle=np.empty(0))
        if brains is None:
            raise ValueError("the neural controller needs one brain per organism")
        return self.think(obs, rng, brains).actions


CONTROLLERS: dict[
    str, type[RandomWalk] | type[NearestFoodSeeker] | type[FleeSeeker] | type[NeuralController]
] = {
    "random_walk": RandomWalk,
    "nearest_food_seeker": NearestFoodSeeker,
    "neural": NeuralController,
    "flee_seeker": FleeSeeker,  # prey: designed evasion (E008)
    # A predator's "food" is prey: its observations hold the nearest prey where a prey's hold
    # the nearest food, so chasing prey is the food seeker's rule, unchanged (D-059).
    "nearest_prey_seeker": NearestFoodSeeker,
}


def make_controller(name: str) -> Controller:
    """Build a controller from its config name (``organisms.controller``)."""
    try:
        return CONTROLLERS[name]()
    except KeyError:
        raise ValueError(
            f"unknown controller {name!r}; choose from {sorted(CONTROLLERS)}"
        ) from None

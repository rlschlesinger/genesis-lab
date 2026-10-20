"""Sensing: turning world state into what each organism knows.

All organisms are sensed at once, from the same positions, before anyone moves (tick step 2).
That is the "snapshot" rule: nobody sees a world that another organism has already changed
this tick.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from genesis.core.geometry import wrap_angle
from genesis.core.spatial import nearest_within_reach

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class BodySenses:
    """What a neural brain needs beyond food (Milestone 4): one entry per organism.

    Filled in by the simulation only when the controller is neural; rule-based controllers
    never see it, so their runs do no extra work and stay byte-identical.
    """

    wall_distance: (
        FloatArray  # distance to the wall straight ahead (brain_inputs.wall_distance_ahead)
    )
    sense_range: FloatArray  # own sense range: food and wall distances are judged against it
    max_turn: FloatArray  # own turning limit: the turn output is a fraction of it
    reproduction_threshold: FloatArray  # own threshold: energy is reported as a fraction of it


@dataclass(frozen=True, slots=True)
class Observations:
    """What every organism senses this tick. Each array has one entry per organism (row i is
    organism i, in the same order as the inputs to ``sense_food``).
    """

    food_found: NDArray[np.bool_]  # is any food within sense range?
    food_distance: FloatArray  # distance to nearest sensed food; inf if none
    food_bearing: FloatArray  # turn needed to face it, radians in [-pi, pi); 0 if none
    energy: FloatArray  # own current energy (unused by Milestone 1 controllers; for later)
    body: BodySenses | None = None  # only for neural controllers (Milestone 4)

    def __len__(self) -> int:
        return len(self.energy)


def sense_food(
    positions: FloatArray,
    headings: FloatArray,
    sense_ranges: FloatArray,
    energies: FloatArray,
    food_positions: FloatArray,
) -> Observations:
    """Find each organism's nearest food within its own sense range.

    Shapes: ``positions`` (n, 2); ``headings``, ``sense_ranges``, ``energies`` (n,);
    ``food_positions`` (m, 2).

    If two food items are exactly equally near, the one with the lower index wins. Food order
    is itself deterministic (see FoodSupply.remove), so this is reproducible.

    Finding the nearest food is delegated to ``genesis.core.spatial``: for small populations
    it computes every organism-to-food distance at once, an (n, m) table via broadcasting; for
    large ones it uses a grid so each organism only checks nearby food. Both give the same
    answer bit for bit (D-036).
    """
    n, m = len(positions), len(food_positions)
    found = np.zeros(n, dtype=bool)
    distance = np.full(n, np.inf)
    bearing = np.zeros(n)

    if n > 0 and m > 0:
        # Food beyond an organism's own range is invisible to it: its distance comes back inf.
        nearest, distance = nearest_within_reach(positions, sense_ranges, food_positions)
        found = np.isfinite(distance)

        # Direction to the nearest food, relative to where the organism is facing. Organisms
        # that found nothing get a placeholder index; their bearing is masked to 0 below.
        dx = food_positions[nearest, 0] - positions[:, 0]
        dy = food_positions[nearest, 1] - positions[:, 1]
        bearing = np.where(found, wrap_angle(np.arctan2(dy, dx) - headings), 0.0)

    return Observations(
        food_found=found,
        food_distance=distance,
        food_bearing=bearing,
        energy=np.asarray(energies, dtype=np.float64).copy(),
    )


def nothing_sensed(energies: FloatArray) -> Observations:
    """Observations for organisms with no senses yet: nothing found, only their own energy.

    What predators perceive until 6.3 gives them senses for prey (D-057). Rule-based
    controllers then behave exactly as they do when no food is in range.
    """
    n = len(energies)
    return Observations(
        food_found=np.zeros(n, dtype=bool),
        food_distance=np.full(n, np.inf),
        food_bearing=np.zeros(n),
        energy=np.asarray(energies, dtype=np.float64).copy(),
    )

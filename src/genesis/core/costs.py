"""Living costs: the energy an organism pays each tick (tick step 5b).

Each cost is a small pure function, so its formula can be read and tested on its own. These
costs are the *trade-offs* that give genes an optimum instead of a free lunch:

    metabolism   metabolic_rate                                   (no trade-off: positive control)
    sensing      sense_cost_per_unit * sense_range                (better senses cost upkeep)
    movement     move_cost_per_distance * distance * (speed / reference_speed) ** exponent

With the default settings (sense_cost_per_unit = 0, speed_cost_exponent = 0) these reproduce
Milestone 1 exactly: x ** 0 is exactly 1.0, and multiplying by 1.0 changes no bits.

Each formula comes in two forms: one organism at a time (``metabolic_cost``...), which states
the rule and is what the tests check, and a whole population at once (``living_costs``), which
the simulation calls. The array form applies the *same* floating-point operations in the same
order to every organism, so it gives the same bits as calling the scalar form in a loop
(``tests/core/test_costs.py`` checks this).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from genesis.core.config import OrganismConfig
from genesis.core.organism import Traits

FloatArray = NDArray[np.float64]


def metabolic_cost(traits: Traits) -> float:
    return traits.metabolic_rate


def sensing_cost(traits: Traits, cfg: OrganismConfig) -> float:
    return cfg.sense_cost_per_unit * traits.sense_range


def movement_cost(
    traits: Traits, distance: float, cfg: OrganismConfig, reference_speed: float
) -> float:
    """Energy for moving ``distance`` this tick.

    The drag factor ``(speed / reference_speed) ** exponent`` uses the organism's top speed
    (a trait), and ``reference_speed`` is the founders' speed, so founders always pay the
    Milestone 1 price and only faster or slower mutants feel the difference. With exponent 1,
    cost per unit distance grows in proportion to speed, so cost per tick at full speed grows
    with speed squared, roughly like air resistance.
    """
    drag = (traits.speed / reference_speed) ** cfg.speed_cost_exponent
    return cfg.move_cost_per_distance * distance * drag


def living_costs(
    metabolic_rates: FloatArray,
    sense_ranges: FloatArray,
    speeds: FloatArray,
    distances: FloatArray,
    cfg: OrganismConfig,
    reference_speed: float,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """The three costs for every organism at once: ``(metabolism, sensing, movement)`` arrays.

    Same formulas as the scalar functions above, element by element. One deliberate detail:
    the drag factor is raised to its power with Python's ``**`` for each organism, not with
    ``np.power``. For most exponents NumPy's power differs from Python's in the last bit
    (measured, D-036), and Milestone 2's results were produced with Python's. Multiplication
    and subtraction have no such problem: one IEEE operation is one IEEE operation.
    """
    exponent = cfg.speed_cost_exponent
    drag = np.array(
        [(speed / reference_speed) ** exponent for speed in speeds.tolist()], dtype=np.float64
    )
    metabolism = np.asarray(metabolic_rates, dtype=np.float64)
    sensing = cfg.sense_cost_per_unit * sense_ranges
    movement = cfg.move_cost_per_distance * distances * drag
    return metabolism, sensing, movement

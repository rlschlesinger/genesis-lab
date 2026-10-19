"""Living costs: the energy an organism pays each tick (tick step 5b).

Each cost is a small pure function, so its formula can be read and tested on its own. These
costs are the *trade-offs* that give genes an optimum instead of a free lunch:

    metabolism   metabolic_rate                                   (no trade-off: positive control)
    sensing      sense_cost_per_unit * sense_range                (better senses cost upkeep)
    movement     move_cost_per_distance * distance * (speed / reference_speed) ** exponent

With the default settings (sense_cost_per_unit = 0, speed_cost_exponent = 0) these reproduce
Milestone 1 exactly: x ** 0 is exactly 1.0, and multiplying by 1.0 changes no bits.
"""

from __future__ import annotations

from genesis.core.config import OrganismConfig
from genesis.core.organism import Traits


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

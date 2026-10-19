"""Organisms: per-individual state and the rules an organism applies to itself.

An organism here is pure state plus bookkeeping. It does not sense, decide or move on its
own: the simulation does that to all organisms together, in the fixed tick order described
in docs/architecture.md. Keeping the organism passive is what makes simultaneous,
order-independent updates possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    # Imported only for type annotations. genome.py imports Traits from this module, so a
    # runtime import here would be circular.
    from genesis.evolution.genome import Genome


@dataclass(frozen=True, slots=True, kw_only=True)
class Traits:
    """The phenotype: the characteristics that actually affect the organism.

    Produced from a Genome by ``genesis.evolution.genome.express``; never built from config
    directly. frozen=True: traits cannot change during a lifetime. Change happens only between
    generations, through mutation.
    """

    speed: float
    sense_range: float
    max_turn: float
    metabolic_rate: float
    reproduction_threshold: float


class DeathCause(StrEnum):
    # StrEnum members behave like strings, so they write cleanly to CSV ("starvation"),
    # while code still gets typo protection: DeathCause.STARVATON is an error.
    STARVATION = "starvation"
    OLD_AGE = "old_age"


@dataclass(slots=True, kw_only=True)
class Organism:
    """One individual.

    slots=True: assigning a misspelled attribute (``org.enrgy = 5``) raises instead of
    silently creating a new one. kw_only=True: construction must name every field, so two
    floats cannot be swapped by position.
    """

    # Identity and lineage: set at birth, never changed.
    id: int
    parent_id: int | None  # None for the founding population
    founder_id: int  # the founding ancestor this organism descends from (itself, if a founder)
    generation: int  # parent's generation + 1; generations overlap (see architecture.md)
    birth_tick: int
    genome: Genome  # genotype: what is inherited
    traits: Traits  # phenotype: express(genome, config), computed once at birth

    # Physical state: changed by the simulation each tick.
    x: float
    y: float
    heading: float  # radians, 0 = +x direction, counter-clockwise positive
    energy: float

    # Life state.
    age: int = 0  # ticks survived; incremented once per tick by the simulation
    alive: bool = True
    death_tick: int | None = None
    death_cause: DeathCause | None = None

    # Lifetime totals, recorded for analysis (spec section 9, "Organism Records").
    energy_gained: float = 0.0  # from food only; starting energy is not "gained"
    energy_spent: float = 0.0  # living costs only: metabolism, sensing and movement
    energy_invested: float = 0.0  # given to offspring plus reproduction overhead
    food_eaten: int = 0
    offspring_count: int = 0

    def spend(self, amount: float) -> float:
        """Deduct up to ``amount`` energy and return what was actually deducted.

        Energy never goes below zero. If an organism with 0.3 EU owes 0.5, only 0.3 leaves it,
        and the return value says so. The energy ledger records the actual amount, which keeps
        the conservation check exact.

        Reaching zero does *not* kill the organism here. Deaths are processed together in one
        tick step, so no organism dies before another has had its turn.
        """
        self._require_alive("spend energy")
        if amount < 0:
            raise ValueError(f"cannot spend negative energy ({amount}); use eat() to gain")
        paid = min(amount, self.energy)
        self.energy -= paid
        self.energy_spent += paid
        return paid

    def eat(self, energy_value: float) -> None:
        """Consume one food item worth ``energy_value`` EU."""
        self._require_alive("eat")
        if energy_value <= 0:
            raise ValueError(f"food must have positive energy, got {energy_value}")
        self.energy += energy_value
        self.energy_gained += energy_value
        self.food_eaten += 1

    @property
    def can_reproduce(self) -> bool:
        return self.alive and self.energy >= self.traits.reproduction_threshold

    def pay_for_offspring(self, transfer: float, overhead: float) -> None:
        """Deduct the cost of one child: ``transfer`` goes to the child, ``overhead`` is lost.

        Kept separate from ``spend`` so that lifetime statistics distinguish energy burned on
        living (``energy_spent``) from energy invested in offspring (``energy_invested``).
        Raises rather than clamping at zero: the config guarantees the threshold exceeds the
        cost, so an organism that can't afford a child here means the caller has a bug.
        """
        self._require_alive("reproduce")
        cost = transfer + overhead
        if cost > self.energy:
            raise RuntimeError(
                f"organism {self.id} cannot afford offspring: has {self.energy}, needs {cost}"
            )
        self.energy -= cost
        self.energy_invested += cost
        self.offspring_count += 1

    def cause_of_death(self, max_age: int | None) -> DeathCause | None:
        """Return why this organism should die now, or None if it survives.

        A query, not an action: it changes nothing, so the simulation can ask about every
        organism first and only then apply the deaths. When both causes apply, starvation is
        reported, because running out of energy is the more informative fact for analysis.
        """
        if self.energy <= 0:
            return DeathCause.STARVATION
        if max_age is not None and self.age >= max_age:
            return DeathCause.OLD_AGE
        return None

    def die(self, tick: int, cause: DeathCause) -> None:
        """Mark this organism dead. Remaining energy stays recorded, not destroyed.

        Whatever energy a dead organism still holds (for example, one dying of old age) is
        removed from the living system by the simulation and logged in the energy ledger.
        """
        self._require_alive("die")
        self.alive = False
        self.death_tick = tick
        self.death_cause = cause

    def _require_alive(self, action: str) -> None:
        # Fails loudly if a dead organism is still being processed. That is always a bug in
        # the tick loop, and catching it here beats discovering corrupted totals later.
        if not self.alive:
            raise RuntimeError(f"organism {self.id} is dead and cannot {action}")


FloatArray = NDArray[np.float64]


def spend_all(
    energy: FloatArray, energy_spent: FloatArray, *costs: FloatArray
) -> tuple[list[FloatArray], FloatArray, FloatArray]:
    """``Organism.spend`` for a whole population at once, one cost after another.

    ``energy[i]`` and ``energy_spent[i]`` belong to organism i; each array in ``costs`` holds
    one kind of cost for every organism, charged in the order given. Returns the amounts
    actually paid for each cost, and the new energy and lifetime-spent arrays.

    Element by element this does exactly what ``spend`` does: ``paid = min(cost, energy)``,
    then ``energy - paid`` and ``energy_spent + paid``, in that order for each cost. The same
    IEEE operations on the same numbers give the same bits, so the simulation can charge
    3,000 organisms in three NumPy calls instead of 9,000 method calls and get the same
    result (D-038). The inputs are not modified.
    """
    paid_each = []
    for cost in costs:
        if cost.size and cost.min() < 0:
            raise ValueError("cannot spend negative energy; use eat() to gain")
        paid = np.minimum(cost, energy)
        energy = energy - paid
        energy_spent = energy_spent + paid
        paid_each.append(paid)
    return paid_each, energy, energy_spent

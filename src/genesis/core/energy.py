"""The energy ledger: conservation accounting for the whole simulation.

Energy lives in two "accounts": living organisms, and uneaten food. It enters and leaves
only through recorded flows:

    in:    food spawned after the start (initial food is part of the starting stock)
    out:   metabolism, sensing, movement, energy still held at death (D-011), reproduction
           overhead, and the share of a caught prey's energy its predator doesn't get (D-058)
    moves: eating (food -> organism), parent -> offspring, and a caught prey's energy to its
           predator. Transfers between accounts, or within one, change neither in nor out.

Every tick the simulation checks: initial stock + in - out == actual stock. A mismatch means
a bug created or destroyed energy, and the run stops instead of producing corrupt data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class EnergyLedgerError(RuntimeError):
    """The energy accounts do not balance: a bug created or destroyed energy."""


@dataclass(slots=True)
class EnergyLedger:
    initial_stock: float
    food_spawned: float = 0.0
    metabolism: float = 0.0
    movement: float = 0.0
    sensing: float = 0.0
    lost_at_death: float = 0.0
    reproduction_overhead: float = 0.0
    predation: float = 0.0  # caught prey's energy not passed on to the predator (D-058)

    @property
    def inflow(self) -> float:
        return self.food_spawned

    @property
    def outflow(self) -> float:
        # math.fsum adds floats with less rounding error than repeated +.
        return math.fsum(
            [
                self.metabolism,
                self.sensing,
                self.movement,
                self.lost_at_death,
                self.reproduction_overhead,
                # 0.0 without predators, and fsum is exact: the total is what it was.
                self.predation,
            ]
        )

    @property
    def expected_stock(self) -> float:
        return self.initial_stock + self.inflow - self.outflow

    @property
    def gross_flow(self) -> float:
        """Everything that has ever passed through the books: start + all in + all out."""
        return self.initial_stock + self.inflow + self.outflow

    @property
    def tolerance(self) -> float:
        """How far actual and expected stock may differ through floating-point rounding alone.

        Rounding error grows with the amount of energy that has *flowed through* the books,
        not with the current stock: a long run can move 300x its stock. So the tolerance
        scales with gross flow (D-026). Measured worst drift over full 20,000-tick runs:
        ~6e-9 EU, at most 4e-15 of gross flow. This tolerance (2.6e-6 EU at 1.6M gross) sits
        ~450x above that and ~1500x below the smallest real error, one missed sensing payment
        at the minimum sense range (1 x 0.004 = 0.004 EU).
        """
        return 1e-6 + 1e-12 * self.gross_flow

    def check(self, actual_stock: float, tick: int) -> None:
        """Raise if ``actual_stock`` differs from what the recorded flows predict by more than
        rounding can explain (``tolerance``)."""
        expected = self.expected_stock
        if abs(actual_stock - expected) > self.tolerance:
            raise EnergyLedgerError(
                f"tick {tick}: energy stock is {actual_stock!r} but the ledger expects "
                f"{expected!r} (difference {actual_stock - expected:+.9g} EU). {self}"
            )

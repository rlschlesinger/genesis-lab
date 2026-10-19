"""The energy ledger: conservation accounting for the whole simulation.

Energy lives in two "accounts": living organisms, and uneaten food. It enters and leaves
only through recorded flows:

    in:    food spawned after the start (initial food is part of the starting stock)
    out:   metabolism, movement, energy still held at death (D-011), reproduction overhead
    moves: eating (food -> organism) and parent -> offspring. Transfers between accounts,
           or within one, change neither in nor out.

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
    lost_at_death: float = 0.0
    reproduction_overhead: float = 0.0

    @property
    def inflow(self) -> float:
        return self.food_spawned

    @property
    def outflow(self) -> float:
        # math.fsum adds floats with less rounding error than repeated +.
        return math.fsum(
            [self.metabolism, self.movement, self.lost_at_death, self.reproduction_overhead]
        )

    @property
    def expected_stock(self) -> float:
        return self.initial_stock + self.inflow - self.outflow

    def check(self, actual_stock: float, tick: int) -> None:
        """Raise if ``actual_stock`` differs from what the recorded flows predict.

        The tolerance allows for floating-point rounding (thousands of additions of values
        like 0.35 that binary can't represent exactly) but is far smaller than any real
        accounting error, such as one missed food item (20 EU by default).
        """
        expected = self.expected_stock
        if not math.isclose(actual_stock, expected, rel_tol=1e-9, abs_tol=1e-6):
            raise EnergyLedgerError(
                f"tick {tick}: energy stock is {actual_stock!r} but the ledger expects "
                f"{expected!r} (difference {actual_stock - expected:+.9g} EU). {self}"
            )

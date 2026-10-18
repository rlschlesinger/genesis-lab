"""The simulation: owns the world and organisms, and runs the tick sequence.

Tick order (docs/architecture.md). Steps marked *later* are wired in by the named increment:

    1. regrow food
    2. sense: every organism observes the same snapshot
    3. decide: the controller turns observations into actions
    4. move
    5. energy costs (metabolism + movement); eating *later: 1.6*
    6. deaths, all decided first and then applied
    7. reproduction *later: 1.7*
    8. record a TickSummary (full metrics *later: 1.8*)
    9. survivors age by one tick; the clock advances
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields

import numpy as np

from genesis.core.config import SimulationConfig
from genesis.core.movement import move
from genesis.core.organism import Organism, Traits
from genesis.core.world import World
from genesis.intelligence.controllers import make_controller
from genesis.intelligence.sensors import sense_food


@dataclass(frozen=True, slots=True)
class RngStreams:
    """One independent random generator per subsystem, all derived from one run seed.

    Field order matters: ``SeedSequence.spawn`` hands out child seeds in order, so a new stream
    must be added at the *end* or every existing stream would change (decision-log D-012).
    """

    setup: np.random.Generator  # founder placement
    food: np.random.Generator  # initial food and regrowth
    controller: np.random.Generator  # controller decisions
    reproduction: np.random.Generator  # newborn placement (1.7)
    tiebreak: np.random.Generator  # food contention ties (1.6)

    @classmethod
    def from_seed(cls, seed: int) -> RngStreams:
        names = [f.name for f in fields(cls)]
        children = np.random.SeedSequence(seed).spawn(len(names))
        return cls(
            **{
                name: np.random.default_rng(child)
                for name, child in zip(names, children, strict=True)
            }
        )


@dataclass(frozen=True, slots=True)
class TickSummary:
    """What happened in one tick. Population and energy are measured at the end of the tick."""

    tick: int
    population: int
    deaths: int
    food_count: int
    food_spawned: int
    mean_energy: float  # NaN when the population is empty: "no value", not zero


class Simulation:
    """One run: a world, its organisms, and the clock.

    Living organisms are kept in ascending ID order. IDs are handed out in increasing order and
    the list is only ever filtered, never reordered, so every per-organism array built from it
    has a stable, reproducible order.
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.rng = RngStreams.from_seed(config.run.seed)
        self.world = World.from_config(config, self.rng.food)
        self.controller = make_controller(config.organisms.controller)
        self.tick = 0
        self._next_id = 0
        self.organisms: list[Organism] = self._make_founders()
        # Dead organisms are kept, not deleted: their lifetime records are experiment data.
        self.dead: list[Organism] = []

    # --- Setup --------------------------------------------------------------------------

    def _new_id(self) -> int:
        new_id = self._next_id
        self._next_id += 1
        return new_id

    def _make_founders(self) -> list[Organism]:
        cfg = self.config.organisms
        n = cfg.initial_count
        traits = Traits.from_config(cfg.traits)
        # Draw all positions, then all headings, as two vectorized calls on the setup stream.
        positions = self.rng.setup.uniform(0.0, [self.world.width, self.world.height], size=(n, 2))
        headings = self.rng.setup.uniform(-np.pi, np.pi, size=n)
        return [
            Organism(
                id=self._new_id(),
                parent_id=None,
                generation=0,
                birth_tick=0,
                traits=traits,
                x=float(x),
                y=float(y),
                heading=float(h),
                energy=cfg.initial_energy,
            )  # fmt: skip
            for (x, y), h in zip(positions, headings, strict=True)
        ]

    # --- Running ------------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        run = self.config.run
        extinct = run.stop_on_extinction and not self.organisms
        return self.tick >= run.max_ticks or extinct

    def run(self) -> list[TickSummary]:
        """Step until ``max_ticks`` or (if configured) extinction. Returns one summary per tick."""
        summaries = []
        while not self.finished:
            summaries.append(self.step())
        return summaries

    def step(self) -> TickSummary:
        """Advance the simulation by exactly one tick."""
        cfg = self.config.organisms
        living = self.organisms

        # 1. Environment.
        food_spawned = self.world.food.regrow(self.rng.food)

        # 2. Snapshot: copy the state into arrays *once*, before anyone moves. Every organism
        #    senses this same frozen picture, so processing order cannot matter.
        positions = np.array([[o.x, o.y] for o in living], dtype=np.float64).reshape(-1, 2)
        headings = np.array([o.heading for o in living], dtype=np.float64)
        energies = np.array([o.energy for o in living], dtype=np.float64)
        speeds = np.array([o.traits.speed for o in living], dtype=np.float64)
        max_turns = np.array([o.traits.max_turn for o in living], dtype=np.float64)
        sense_ranges = np.array([o.traits.sense_range for o in living], dtype=np.float64)

        observations = sense_food(
            positions, headings, sense_ranges, energies, self.world.food.positions
        )

        # 3. Decide.
        actions = self.controller.decide(observations, self.rng.controller)

        # 4. Move, then write the results back to each organism.
        moved = move(positions, headings, actions, speeds, max_turns, self.world)
        for org, (x, y), heading in zip(living, moved.positions, moved.headings, strict=True):
            org.x, org.y, org.heading = float(x), float(y), float(heading)

        # 5. Energy costs. Eating is added here in increment 1.6.
        for org, distance in zip(living, moved.distances, strict=True):
            org.spend(org.traits.metabolic_rate)
            org.spend(cfg.move_cost_per_distance * float(distance))

        # 6. Deaths: ask every organism first, then apply. Nobody dies mid-update.
        causes = [org.cause_of_death(cfg.max_age) for org in living]
        survivors = []
        for org, cause in zip(living, causes, strict=True):
            if cause is None:
                survivors.append(org)
            else:
                org.die(self.tick, cause)
                self.dead.append(org)

        # 7. Reproduction is added here in increment 1.7.

        # 8. Record.
        summary = TickSummary(
            tick=self.tick,
            population=len(survivors),
            deaths=len(living) - len(survivors),
            food_count=self.world.food.count,
            food_spawned=food_spawned,
            mean_energy=(float(np.mean([o.energy for o in survivors])) if survivors else math.nan),
        )

        # 9. Advance time.
        for org in survivors:
            org.age += 1
        self.organisms = survivors
        self.tick += 1
        return summary

    # --- Inspection ---------------------------------------------------------------------

    def state_digest(self) -> str:
        """A SHA-256 fingerprint of the full simulation state.

        Two simulations have the same digest only if every food position and every organism's
        id, position, heading, energy, age and alive status match bit for bit. Used to check
        determinism, and later recorded in run metadata.
        """
        h = hashlib.sha256()
        h.update(np.int64(self.tick).tobytes())
        h.update(np.ascontiguousarray(self.world.food.positions).tobytes())
        for org in [*self.organisms, *self.dead]:
            h.update(
                np.array(
                    [org.id, org.x, org.y, org.heading, org.energy, org.age, org.alive],
                    dtype=np.float64,
                ).tobytes()
            )
        return h.hexdigest()

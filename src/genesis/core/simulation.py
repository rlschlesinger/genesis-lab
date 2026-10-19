"""The simulation: owns the world and organisms, and runs the tick sequence.

Tick order (docs/architecture.md):

    1. regrow food
    2. sense: every organism observes the same snapshot
    3. decide: the controller turns observations into actions
    4. move
    5. eat (closest pairs first), then pay energy costs (metabolism + movement)
    6. deaths, all decided first and then applied
    7. reproduction: eligible survivors each produce one exact copy; newborns join the
       population but have not acted, and will first act next tick
    8. check the energy ledger; record a TickSummary (full metrics in increment 1.8)
    9. organisms that were alive at the start of the tick age by one; the clock advances
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields

import numpy as np

from genesis.core.config import SimulationConfig
from genesis.core.energy import EnergyLedger
from genesis.core.feeding import resolve_feeding
from genesis.core.movement import move
from genesis.core.organism import Organism, Traits
from genesis.core.world import World
from genesis.evolution.reproduction import place_offspring, select_parents
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
    reproduction: np.random.Generator  # who reproduces at the cap; newborn placement
    tiebreak: np.random.Generator  # food contention ties

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
    population: int  # includes this tick's newborns
    births: int
    deaths: int
    food_count: int
    food_spawned: int
    food_eaten: int
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
        # Opened after founders and initial food exist: they make up the starting stock.
        self.ledger = EnergyLedger(initial_stock=self.energy_stock())

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
            )
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

        food_value = self.config.food.energy_value

        # 1. Environment.
        food_spawned = self.world.food.regrow(self.rng.food)
        self.ledger.food_spawned += food_spawned * food_value

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

        # 5a. Eat, using post-move positions. Eating is a transfer between the two energy
        #     accounts (food -> organism), so the ledger's in/out totals don't change.
        meals = resolve_feeding(
            moved.positions, self.world.food.positions, self.config.food.eat_radius,
            self.rng.tiebreak,
        )  # fmt: skip
        for i in meals.eaters:
            living[i].eat(food_value)
        self.world.food.remove(meals.foods)

        # 5b. Pay costs *after* eating, so a nearly-empty organism that reaches food gets to
        #     eat before its energy hits zero. spend() returns what was actually paid, and
        #     that (not the amount requested) is what the ledger records.
        for org, distance in zip(living, moved.distances, strict=True):
            self.ledger.metabolism += org.spend(org.traits.metabolic_rate)
            self.ledger.movement += org.spend(cfg.move_cost_per_distance * float(distance))

        # 6. Deaths: ask every organism first, then apply. Nobody dies mid-update.
        causes = [org.cause_of_death(cfg.max_age) for org in living]
        survivors = []
        for org, cause in zip(living, causes, strict=True):
            if cause is None:
                survivors.append(org)
            else:
                # Energy still held at death leaves the system (D-011). The organism's own
                # record keeps the value, so analysis can see what it died with.
                self.ledger.lost_at_death += org.energy
                org.die(self.tick, cause)
                self.dead.append(org)

        # 7. Reproduction. Only survivors are candidates, and newborns are added after them,
        #    so a newborn cannot act or reproduce in the tick it was born.
        newborns = self._reproduce(survivors)
        self.organisms = survivors + newborns  # still ascending ID order: new IDs are larger

        # 8. Check conservation, then record. A failed check raises EnergyLedgerError.
        self.ledger.check(self.energy_stock(), self.tick)
        population = self.organisms
        summary = TickSummary(
            tick=self.tick,
            population=len(population),
            births=len(newborns),
            deaths=len(living) - len(survivors),
            food_count=self.world.food.count,
            food_spawned=food_spawned,
            food_eaten=len(meals),
            mean_energy=(
                float(np.mean([o.energy for o in population])) if population else math.nan
            ),
        )

        # 9. Advance time. Newborns stay at age 0: they have not lived through a tick yet.
        for org in survivors:
            org.age += 1
        self.tick += 1
        return summary

    def _reproduce(self, candidates: list[Organism]) -> list[Organism]:
        """Create this tick's offspring. Each eligible organism has at most one child."""
        cfg = self.config.organisms
        eligible = np.array([o.can_reproduce for o in candidates], dtype=bool)
        room = cfg.max_population - len(candidates)
        chosen = select_parents(eligible, room, self.rng.reproduction)
        if len(chosen) == 0:
            return []

        parents = [candidates[i] for i in chosen]
        positions, headings = place_offspring(
            np.array([[p.x, p.y] for p in parents], dtype=np.float64),
            np.array([p.traits.speed for p in parents], dtype=np.float64),
            self.world,
            self.rng.reproduction,
        )
        newborns = []
        for parent, (x, y), heading in zip(parents, positions, headings, strict=True):
            parent.pay_for_offspring(cfg.offspring_energy, cfg.reproduction_overhead)
            # The transfer stays inside the organism account; only the overhead leaves.
            self.ledger.reproduction_overhead += cfg.reproduction_overhead
            newborns.append(
                Organism(
                    id=self._new_id(),
                    parent_id=parent.id,
                    generation=parent.generation + 1,
                    birth_tick=self.tick,
                    # Exact copy (Milestone 1). Traits are frozen, so sharing one object
                    # between parent and child is safe: neither can change it.
                    traits=parent.traits,
                    x=float(x),
                    y=float(y),
                    heading=float(heading),
                    energy=cfg.offspring_energy,
                )
            )
        return newborns

    # --- Inspection ---------------------------------------------------------------------

    def energy_stock(self) -> float:
        """Total energy currently in the system: living organisms plus uneaten food."""
        in_organisms = math.fsum(o.energy for o in self.organisms)
        return in_organisms + self.world.food.count * self.config.food.energy_value

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

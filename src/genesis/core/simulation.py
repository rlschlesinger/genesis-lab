"""The simulation: owns the world and organisms, and runs the tick sequence.

Tick order (docs/architecture.md):

    1. regrow food
    2. sense: every organism observes the same snapshot
    3. decide: the controller turns observations into actions
    4. move
    5. eat (closest pairs first), then pay living costs (metabolism, sensing, movement)
    6. deaths, all decided first and then applied
    7. reproduction: eligible survivors each produce one child with a mutated copy of their
       genome (an exact copy when mutation is off); newborns join the
       population but have not acted, and will first act next tick
    8. check the energy ledger; record a TickSummary
    9. organisms that were alive at the start of the tick age by one; the clock advances
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields, replace
from itertools import compress

import numpy as np
from numpy.typing import NDArray

from genesis.core.config import SimulationConfig
from genesis.core.costs import living_costs
from genesis.core.energy import EnergyLedger
from genesis.core.feeding import resolve_feeding
from genesis.core.movement import move
from genesis.core.organism import DeathCause, Organism, spend_all
from genesis.core.world import World
from genesis.evolution.brain import founder_brains, mutate_brain
from genesis.evolution.genome import Genome, express
from genesis.evolution.mutation import mutate
from genesis.evolution.reproduction import place_offspring, select_parents
from genesis.intelligence.brain_inputs import wall_distance_ahead
from genesis.intelligence.controllers import Actions, Thought, make_controller
from genesis.intelligence.neural import Brain, BrainStack
from genesis.intelligence.sensors import BodySenses, Observations, sense_food


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
    mutation: np.random.Generator  # offspring genome mutation (added in Milestone 2, at the end)
    brain: np.random.Generator  # founders' brains and brain mutation (Milestone 4, at the end)

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
    lineages: int  # distinct founder lineages still alive
    mutations: int  # gene changes in this tick's newborns


@dataclass(frozen=True, slots=True)
class MutationEvent:
    """One gene change at one birth: the record that makes every genome traceable."""

    tick: int
    parent_id: int
    child_id: int
    gene: str
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class Decision:
    """This tick's decision step, kept for recording behaviour (one entry per organism that
    acted, in ID order). References to arrays the tick computed anyway: storing it costs
    nothing and changes nothing."""

    observations: Observations
    actions: Actions  # as requested; movement clips turn to +/- max_turn, throttle to [0, 1]
    max_turn: NDArray[np.float64]
    # Neural runs: the controller's whole computation (inputs, activations), exactly as used.
    # This is what `genesis inspect` prints, so it can never disagree with the simulation.
    thought: Thought | None = None


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened to one organism during a tick (for the optional event log).

    ``other_id`` is the parent for a birth; ``energy`` is what the newborn received, what the
    deceased held, or what the meal gave; ``detail`` is the cause of a death.
    """

    tick: int
    kind: str  # "meal", "death" or "birth", in the order they happen within a tick
    organism_id: int
    other_id: int | None
    energy: float
    x: float
    y: float
    detail: str | None


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
        self._neural = config.organisms.controller == "neural"
        # Founders' speed: the drag cost is relative to it (core/costs.py).
        self._reference_speed = config.genome.speed.initial
        self.tick = 0
        self._next_id = 0
        self.organisms: list[Organism] = self._make_founders()
        # Dead organisms are kept, not deleted: their lifetime records are experiment data.
        self.dead: list[Organism] = []
        # Every gene change at every birth, in the order they happened.
        self.mutation_log: list[MutationEvent] = []
        # This tick's meals, deaths and births, in the order they happened. Always collected
        # (a handful per tick); the recorder decides which kinds to keep.
        self.events_this_tick: list[Event] = []
        # This tick's observations and actions, for behaviour metrics (None before tick 0).
        self.last_decision: Decision | None = None
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
        # All founders share one genome (no initial variation): any variation that appears
        # later comes from mutation alone. Brains are the exception (D-041): each founder
        # gets its own random weights, drawn from the brain stream after placement.
        genome = Genome.from_config(self.config.genome)
        traits = express(genome, self.config.genome)
        # Draw all positions, then all headings, as two vectorized calls on the setup stream.
        positions = self.rng.setup.uniform(0.0, [self.world.width, self.world.height], size=(n, 2))
        headings = self.rng.setup.uniform(-np.pi, np.pi, size=n)
        brain_cfg = self.config.brain
        if brain_cfg is None:
            brains = [None] * n
        elif brain_cfg.founder_weights is not None:
            # Given brains (e.g. evolved elsewhere, E007): nothing is drawn from the stream.
            brains = [Brain.from_vector(w) for w in brain_cfg.founder_weights]
        else:
            brains = founder_brains(n, brain_cfg, self.rng.brain)
        founders = []
        for (x, y), h, brain in zip(positions, headings, brains, strict=True):
            new_id = self._new_id()
            founders.append(
                Organism(
                    id=new_id,
                    parent_id=None,
                    founder_id=new_id,  # each founder starts its own lineage
                    generation=0,
                    birth_tick=0,
                    genome=genome,
                    traits=traits,
                    brain=brain,
                    x=float(x),
                    y=float(y),
                    heading=float(h),
                    energy=cfg.initial_energy,
                )
            )
        return founders

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
        events: list[Event] = []

        # 1. Environment.
        food_spawned = self.world.food.regrow(self.rng.food)
        self.ledger.food_spawned += food_spawned * food_value

        # 2. Snapshot: copy the state into arrays *once*, before anyone moves. Every organism
        #    senses this same frozen picture, so processing order cannot matter. The organisms
        #    stay the source of truth; these arrays are this tick's working copy (D-038).
        positions = np.column_stack(
            [
                np.array([o.x for o in living], dtype=np.float64),
                np.array([o.y for o in living], dtype=np.float64),
            ]
        ).reshape(-1, 2)
        headings = np.array([o.heading for o in living], dtype=np.float64)
        energies = np.array([o.energy for o in living], dtype=np.float64)
        energy_spent = np.array([o.energy_spent for o in living], dtype=np.float64)
        traits = [o.traits for o in living]
        speeds = np.array([t.speed for t in traits], dtype=np.float64)
        max_turns = np.array([t.max_turn for t in traits], dtype=np.float64)
        sense_ranges = np.array([t.sense_range for t in traits], dtype=np.float64)
        metabolic_rates = np.array([t.metabolic_rate for t in traits], dtype=np.float64)
        thresholds = np.array([t.reproduction_threshold for t in traits], dtype=np.float64)

        observations = sense_food(
            positions, headings, sense_ranges, energies, self.world.food.positions
        )

        # 3. Decide. A neural controller also needs each organism's brain and what it knows
        #    about its own body (D-042); rule-based controllers get exactly what they always
        #    did, so their runs are unchanged.
        if self._neural and living:
            observations = replace(
                observations,
                body=BodySenses(
                    wall_distance=wall_distance_ahead(
                        positions, headings, self.world.width, self.world.height
                    ),
                    sense_range=sense_ranges,
                    max_turn=max_turns,
                    reproduction_threshold=thresholds,
                ),
            )
            brains = BrainStack.of([o.brain for o in living])
            # think() is what decide() calls; keeping its result costs nothing extra.
            thought = self.controller.think(observations, self.rng.controller, brains)
            actions = thought.actions
        else:
            thought = None
            actions = self.controller.decide(observations, self.rng.controller)
        self.last_decision = Decision(observations, actions, max_turns, thought)

        # 4. Move, then write the results back to each organism. tolist() hands back plain
        #    Python floats with the same values; it is many times faster than converting one
        #    NumPy scalar at a time.
        moved = move(positions, headings, actions, speeds, max_turns, self.world)
        xs, ys = moved.positions[:, 0].tolist(), moved.positions[:, 1].tolist()
        for org, x, y, heading in zip(living, xs, ys, moved.headings.tolist(), strict=True):
            org.x, org.y, org.heading = x, y, heading

        # 5a. Eat, using post-move positions. Eating is a transfer between the two energy
        #     accounts (food -> organism), so the ledger's in/out totals don't change.
        meals = resolve_feeding(
            moved.positions, self.world.food.positions, self.config.food.eat_radius,
            self.rng.tiebreak,
        )  # fmt: skip
        for i in meals.eaters:
            eater = living[i]
            eater.eat(food_value)
            events.append(
                Event(self.tick, "meal", eater.id, None, food_value, eater.x, eater.y, None)
            )
        self.world.food.remove(meals.foods)
        # The working copy gets the same meals: the same addition, so the same value.
        energies[meals.eaters] += food_value

        # 5b. Pay costs *after* eating, so a nearly-empty organism that reaches food gets to
        #     eat before its energy hits zero. spend_all() returns what was actually paid, and
        #     that (not the amount requested) is what the ledger records.
        #     Order matters only when energy runs out mid-payment (spending never goes below
        #     zero): metabolism first, then sensing, then movement. See core/costs.py.
        #     Each flow's payments are summed exactly (math.fsum) and added to the ledger once
        #     per tick. Adding millions of small payments one by one to a running total of
        #     ~10^6 loses a sliver to rounding each time, and those slivers add up (D-026).
        costs = living_costs(
            metabolic_rates, sense_ranges, speeds, moved.distances, cfg, self._reference_speed
        )
        paid, energies, energy_spent = spend_all(energies, energy_spent, *costs)
        self.ledger.metabolism += math.fsum(paid[0].tolist())
        self.ledger.sensing += math.fsum(paid[1].tolist())
        self.ledger.movement += math.fsum(paid[2].tolist())
        spent_each = energy_spent.tolist()
        for org, energy, spent in zip(living, energies.tolist(), spent_each, strict=True):
            org.energy, org.energy_spent = energy, spent

        # 6. Deaths: decide for every organism first, then apply. Nobody dies mid-update.
        #    Same rule as Organism.cause_of_death: starvation first, then old age.
        starved = energies <= 0.0
        dying = starved
        if cfg.max_age is not None:
            ages = np.array([o.age for o in living], dtype=np.int64)
            dying = starved | (ages >= cfg.max_age)
        survivors = list(compress(living, ~dying))
        lost = []
        for i in np.flatnonzero(dying).tolist():
            org = living[i]
            cause = DeathCause.STARVATION if starved[i] else DeathCause.OLD_AGE
            # Energy still held at death leaves the system (D-011). The organism's own
            # record keeps the value, so analysis can see what it died with.
            lost.append(org.energy)
            events.append(
                Event(self.tick, "death", org.id, None, org.energy, org.x, org.y, str(cause))
            )
            org.die(self.tick, cause)
            self.dead.append(org)
        # Summed exactly and added to the ledger once per tick, like the living costs (D-026).
        self.ledger.lost_at_death += math.fsum(lost)

        # 7. Reproduction. Only survivors are candidates, and newborns are added after them,
        #    so a newborn cannot act or reproduce in the tick it was born. Eligibility is
        #    Organism.can_reproduce evaluated on the arrays: alive (a survivor) and
        #    energy >= threshold.
        logged_before = len(self.mutation_log)
        alive = ~dying
        eligible = energies[alive] >= thresholds[alive]
        newborns = self._reproduce(survivors, eligible)
        mutations_this_tick = len(self.mutation_log) - logged_before
        self.organisms = survivors + newborns  # still ascending ID order: new IDs are larger
        for child in newborns:
            events.append(
                Event(self.tick, "birth", child.id, child.parent_id, child.energy, child.x,
                      child.y, None)
            )  # fmt: skip
        self.events_this_tick = events

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
            # A set is used only to count distinct values, never iterated, so its
            # unordered nature cannot affect results.
            lineages=len({o.founder_id for o in population}),
            mean_energy=(
                float(np.mean([o.energy for o in population])) if population else math.nan
            ),
            mutations=mutations_this_tick,
        )

        # 9. Advance time. Newborns stay at age 0: they have not lived through a tick yet.
        for org in survivors:
            org.age += 1
        self.tick += 1
        return summary

    def _reproduce(
        self, candidates: list[Organism], eligible: NDArray[np.bool_] | None = None
    ) -> list[Organism]:
        """Create this tick's offspring. Each eligible organism has at most one child.

        ``eligible[i]`` says whether ``candidates[i]`` may reproduce; when omitted it is read
        from each organism (``can_reproduce``).
        """
        cfg = self.config.organisms
        if eligible is None:
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

            # Inheritance. With mutation disabled, mutate() returns the parent's own genome
            # and draws nothing, which is exactly Milestone 1's behaviour.
            genome, changes = mutate(
                parent.genome, self.config.genome, self.config.mutation, self.rng.mutation
            )
            # Unchanged genome: reuse the parent's traits (identical, and frozen).
            traits = (
                parent.traits if genome is parent.genome else express(genome, self.config.genome)
            )
            # The brain is inherited the same way, from its own stream (D-041). Its changes
            # are not logged in mutation_log, which is about the named genes; 4.5 records
            # every brain at birth instead. Mutation disabled: the parent's brain, unchanged.
            brain = parent.brain
            if brain is not None and self.config.mutation.enabled:
                brain, _ = mutate_brain(brain, self.config.brain, self.rng.brain)
            child_id = self._new_id()
            for change in changes:
                self.mutation_log.append(
                    MutationEvent(
                        self.tick, parent.id, child_id, change.gene, change.before, change.after
                    )
                )
            newborns.append(
                Organism(
                    id=child_id,
                    parent_id=parent.id,
                    founder_id=parent.founder_id,
                    generation=parent.generation + 1,
                    birth_tick=self.tick,
                    genome=genome,
                    traits=traits,
                    brain=brain,
                    x=float(x),
                    y=float(y),
                    heading=float(heading),
                    energy=cfg.offspring_energy,
                )
            )
        # The transfer stays inside the organism account; only the overhead leaves. One
        # multiplication per tick, not one addition per birth (D-026).
        self.ledger.reproduction_overhead += len(newborns) * cfg.reproduction_overhead
        return newborns

    # --- Inspection ---------------------------------------------------------------------

    def energy_stock(self) -> float:
        """Total energy currently in the system: living organisms plus uneaten food."""
        in_organisms = math.fsum(o.energy for o in self.organisms)
        return in_organisms + self.world.food.count * self.config.food.energy_value

    def state_digest(self) -> str:
        """A SHA-256 fingerprint of the full simulation state.

        Two simulations have the same digest only if every food position and every organism's
        id, position, heading, energy, age, alive status and genes match bit for bit. Used to
        check determinism, and recorded in run metadata.

        Genes are included because some never affect behaviour: two runs differing only in a
        neutral marker would otherwise look identical forever. Brain weights are included for
        organisms that have one; organisms without a brain add nothing, so digests of
        rule-based runs are unchanged by Milestone 4.
        """
        h = hashlib.sha256()
        h.update(np.int64(self.tick).tobytes())
        h.update(np.ascontiguousarray(self.world.food.positions).tobytes())
        for org in [*self.organisms, *self.dead]:
            genes = list(org.genome.as_dict().values())
            h.update(
                np.array(
                    [org.id, org.x, org.y, org.heading, org.energy, org.age, org.alive, *genes],
                    dtype=np.float64,
                ).tobytes()
            )
            if org.brain is not None:
                h.update(org.brain.to_vector().tobytes())
        return h.hexdigest()

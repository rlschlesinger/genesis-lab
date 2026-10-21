"""The simulation: owns the world and organisms, and runs the tick sequence.

Tick order (docs/architecture.md):

    1. regrow food
    2. sense: every organism observes the same snapshot
    3. decide: the controller turns observations into actions
    4. move
    5. eat (closest pairs first); predators catch prey; then pay living costs (metabolism,
       sensing, movement)
    6. deaths, all decided first and then applied
    7. reproduction: eligible survivors each produce one child with a mutated copy of their
       genome (an exact copy when mutation is off); newborns join the
       population but have not acted, and will first act next tick
    8. check the energy ledger; record a TickSummary
    9. organisms that were alive at the start of the tick age by one; the clock advances

Predators (Milestone 6, D-057), when configured, are a second list of organisms that go
through the same steps beside the prey: they sense the same start-of-tick snapshot, move,
pay their own costs, die and reproduce by the same rules with their own settings. They don't
eat food: after the prey have eaten (5a), predators strike at prey within reach (D-058);
a caught prey dies there and does nothing more that tick. ``sim.organisms`` and everything
recorded from it remain the prey.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields, replace
from itertools import compress

import numpy as np
from numpy.typing import NDArray

from genesis.core.config import BrainConfig, GenomeConfig, OrganismConfig, SimulationConfig
from genesis.core.costs import living_costs
from genesis.core.energy import EnergyLedger
from genesis.core.feeding import resolve_feeding
from genesis.core.movement import move
from genesis.core.organism import DeathCause, Organism, spend_all
from genesis.core.predation import resolve_strikes
from genesis.core.world import World
from genesis.evolution.brain import founder_brains, mutate_brain
from genesis.evolution.genome import Genome, express
from genesis.evolution.mutation import mutate, mutate_value
from genesis.evolution.reproduction import place_offspring, select_parents
from genesis.intelligence.brain_inputs import PREY_INPUT_NAMES, wall_distance_ahead
from genesis.intelligence.controllers import Actions, Thought, make_controller
from genesis.intelligence.neural import N_HIDDEN, N_INPUTS, N_OUTPUTS, Brain, BrainStack
from genesis.intelligence.sensors import (
    BodySenses,
    KindSenses,
    Observations,
    sense_food,
    sense_threats,
)


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
    # Everything random about predators (Milestone 6, at the end), split into PredatorStreams.
    # Unused without predators. Because prey never draw from it, a world with predators and
    # one without, on the same seed, start with the same prey and the same food (E008's
    # matched pairs).
    predators: np.random.Generator
    # Two foods (06B, at the end): which kind each new food item is, and diet mutation.
    # Unused with one food; food positions come from the food stream either way.
    resources: np.random.Generator

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
class PredatorStreams:
    """The predators' own generators, one per subsystem, spawned from ``RngStreams.predators``.

    The same rule as RngStreams, one level down: a predator subsystem that draws more (6.2's
    capture ties, say) never shifts another's sequence. New streams go at the end.
    """

    setup: np.random.Generator  # founder placement
    controller: np.random.Generator  # predators' decisions
    reproduction: np.random.Generator  # who reproduces at the cap; newborn placement
    mutation: np.random.Generator  # offspring genome mutation
    capture: np.random.Generator  # strike ties and success (6.2, D-058)
    brain: np.random.Generator  # founders' brains and brain mutation (6.3, D-059)

    @classmethod
    def from_generator(cls, parent: np.random.Generator) -> PredatorStreams:
        return cls(*parent.spawn(len(fields(cls))))


@dataclass(frozen=True, slots=True)
class Bodies:
    """One species' state at the start of a tick, copied into arrays once (tick step 2).

    Row i is organism i of the list it was taken from, in ascending ID order. The organisms stay
    the source of truth; these arrays are the tick's working copy (D-038).
    """

    positions: NDArray[np.float64]  # (n, 2)
    headings: NDArray[np.float64]
    energies: NDArray[np.float64]
    energy_spent: NDArray[np.float64]
    speeds: NDArray[np.float64]
    max_turns: NDArray[np.float64]
    sense_ranges: NDArray[np.float64]
    metabolic_rates: NDArray[np.float64]
    thresholds: NDArray[np.float64]

    @classmethod
    def of(cls, living: list[Organism]) -> Bodies:
        traits = [o.traits for o in living]
        return cls(
            positions=np.column_stack(
                [
                    np.array([o.x for o in living], dtype=np.float64),
                    np.array([o.y for o in living], dtype=np.float64),
                ]
            ).reshape(-1, 2),
            headings=np.array([o.heading for o in living], dtype=np.float64),
            energies=np.array([o.energy for o in living], dtype=np.float64),
            energy_spent=np.array([o.energy_spent for o in living], dtype=np.float64),
            speeds=np.array([t.speed for t in traits], dtype=np.float64),
            max_turns=np.array([t.max_turn for t in traits], dtype=np.float64),
            sense_ranges=np.array([t.sense_range for t in traits], dtype=np.float64),
            metabolic_rates=np.array([t.metabolic_rate for t in traits], dtype=np.float64),
            thresholds=np.array([t.reproduction_threshold for t in traits], dtype=np.float64),
        )


@dataclass(frozen=True, slots=True)
class Lineage:
    """Where a species' inheritance comes from: what ``_reproduce`` needs for one species."""

    body: OrganismConfig  # costs, offspring energy, population cap
    genome: GenomeConfig  # gene ranges for mutation and expression
    reproduction: np.random.Generator
    mutation: np.random.Generator
    brain: BrainConfig | None = None
    brain_rng: np.random.Generator | None = None


@dataclass(frozen=True, slots=True)
class PredatorSummary:
    """The predators' side of one tick (TickSummary describes the prey). Measured at the end
    of the tick, like TickSummary. Recorded from 6.4; kept separate so that adding it changed
    no column of ticks.csv."""

    tick: int
    population: int  # includes this tick's newborns
    births: int
    deaths: int
    mean_energy: float  # NaN when there are no predators left
    lineages: int
    attempts: int  # strikes at prey within reach (6.2)
    captures: int  # strikes that caught their prey


@dataclass(frozen=True, slots=True)
class Strike:
    """One predator's strike at one prey (6.2), caught or not: a row of strikes.csv (6.4)."""

    tick: int
    predator_id: int
    prey_id: int
    caught: bool
    prey_energy: float  # what the prey held when struck (this tick's meal included)
    predator_gain: float  # what the predator gained: 0 when the prey escaped


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
        self._two_foods = config.resources is not None
        self.world = World.from_config(
            config, self.rng.food, self.rng.resources if self._two_foods else None
        )
        self.controller = make_controller(config.organisms.controller)
        self._neural = config.organisms.controller == "neural"
        # Prey brains have 10 inputs in a world with predators (even none), 7 otherwise (D-059).
        self._prey_inputs = len(PREY_INPUT_NAMES) if config.predators is not None else N_INPUTS
        # Founders' speed: the drag cost is relative to it (core/costs.py).
        self._reference_speed = config.genome.speed.initial
        self.tick = 0
        self._next_id = 0
        self.organisms: list[Organism] = self._make_founders()
        # Dead organisms are kept, not deleted: their lifetime records are experiment data.
        self.dead: list[Organism] = []
        self._prey = Lineage(
            config.organisms, config.genome, self.rng.reproduction, self.rng.mutation,
            config.brain, self.rng.brain,
        )  # fmt: skip
        # Predators (D-057): a second list, after the prey founders in ID order. Empty, and
        # never touched, when the config has no predators section.
        self.predator_rng = PredatorStreams.from_generator(self.rng.predators)
        hunters = config.predators
        self.predators: list[Organism] = []
        self.dead_predators: list[Organism] = []
        self.predator_summary: PredatorSummary | None = None
        self.predator_events_this_tick: list[Event] = []
        self.predator_mutation_log: list[MutationEvent] = []
        self.strikes_this_tick: list[Strike] = []  # every strike, in predator order
        self.meals_b_this_tick = 0  # two foods: meals of kind B this tick (A = food_eaten - B)
        # The predators' latest decision, as last_decision is the prey's (None until tick 0).
        self.last_predator_decision: Decision | None = None
        if hunters is not None:
            self.predator_controller = make_controller(hunters.controller)
            self._neural_predators = hunters.controller == "neural"
            self._predator_reference_speed = hunters.genome.speed.initial
            self._predator_lineage = Lineage(
                hunters, hunters.genome, self.predator_rng.reproduction,
                self.predator_rng.mutation, hunters.brain, self.predator_rng.brain,
            )  # fmt: skip
            self.predators = self._make_predator_founders()
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
            shape = (self._prey_inputs, N_HIDDEN, N_OUTPUTS)
            brains = [Brain.from_vector(w, shape) for w in brain_cfg.founder_weights]
        else:
            brains = founder_brains(n, brain_cfg, self.rng.brain, self._prey_inputs)
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
                    # Two foods: every founder starts with the configured diet, as genes do.
                    diet=self.config.resources.diet.initial if self._two_foods else None,
                    x=float(x),
                    y=float(y),
                    heading=float(h),
                    energy=cfg.initial_energy,
                )
            )
        return founders

    def _digests(self, org: Organism) -> tuple[float, float]:
        """Two foods: the share of a meal of A, and of B, this organism keeps (D-063).

        ``(1 - d) ** k`` and ``d ** k``, Python's ``**`` on plain floats. With a neutral diet
        gene everyone digests as the founders do, whatever their own ``d``.
        """
        resources = self.config.resources
        d = resources.diet.initial if resources.diet.neutral else org.diet
        k = resources.exponent
        return (1.0 - d) ** k, d**k

    def _make_predator_founders(self) -> list[Organism]:
        """Predator founders, placed like prey founders but from the predators' own stream.
        They share one genome (no initial variation), as prey founders do."""
        cfg = self.config.predators
        assert cfg is not None
        n = cfg.initial_count
        genome = Genome.from_config(cfg.genome)
        traits = express(genome, cfg.genome)
        rng = self.predator_rng.setup
        positions = rng.uniform(0.0, [self.world.width, self.world.height], size=(n, 2))
        headings = rng.uniform(-np.pi, np.pi, size=n)
        # Brains as for prey (D-041): one random brain each, from the predators' own stream.
        if cfg.brain is None:
            brains = [None] * n
        elif cfg.brain.founder_weights is not None:
            brains = [Brain.from_vector(w) for w in cfg.brain.founder_weights]
        else:
            brains = founder_brains(n, cfg.brain, self.predator_rng.brain)
        founders = []
        for (x, y), h, brain in zip(positions, headings, brains, strict=True):
            new_id = self._new_id()
            founders.append(
                Organism(
                    id=new_id, parent_id=None, founder_id=new_id, generation=0, birth_tick=0,
                    genome=genome, traits=traits, brain=brain, x=float(x), y=float(y),
                    heading=float(h), energy=cfg.initial_energy,
                )
            )  # fmt: skip
        return founders

    # --- Running ------------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        run = self.config.run
        # Extinct means nobody at all: prey gone but predators left still has a story to tell
        # (the predators starve), and predators gone leaves a prey-only world running.
        extinct = run.stop_on_extinction and not self.organisms and not self.predators
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
        started = len(living)  # prey alive at the start of the tick (some may be caught)

        food_value = self.config.food.energy_value
        events: list[Event] = []

        # 1. Environment.
        food_spawned = self.world.food.regrow(self.rng.food)
        self.ledger.food_spawned += food_spawned * food_value

        # 2. Snapshot: copy the state into arrays *once*, before anyone moves. Every organism
        #    senses this same frozen picture, so processing order cannot matter. The organisms
        #    stay the source of truth; these arrays are this tick's working copy (D-038).
        prey = Bodies.of(living)
        positions, headings, energies = prey.positions, prey.headings, prey.energies
        energy_spent, speeds, max_turns = prey.energy_spent, prey.speeds, prey.max_turns
        sense_ranges, metabolic_rates = prey.sense_ranges, prey.metabolic_rates
        thresholds = prey.thresholds
        hunters = self.predators
        hunting = self.config.predators is not None
        if hunting:
            pred = Bodies.of(hunters)

        observations = sense_food(
            positions, headings, sense_ranges, energies, self.world.food.positions
        )

        # 3. Decide. A neural controller also needs each organism's brain and what it knows
        #    about its own body (D-042); rule-based controllers get exactly what they always
        #    did, so their runs are unchanged.
        # In a world with predators, prey that can use it (neural brains, and the designed
        # flee rule) also sense the nearest predator, from the same start-of-tick snapshot
        # (D-059, D-062). With none present it is never found. Other prey aren't told.
        threat = None
        if hunting and living and cfg.controller in ("neural", "flee_seeker"):
            threat = sense_threats(positions, headings, sense_ranges, pred.positions)
        if self._neural and living:
            observations = replace(
                observations,
                threat=threat,
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
            if threat is not None:
                observations = replace(observations, threat=threat)
            if cfg.controller == "diet_seeker":
                observations = replace(observations, kinds=self._sense_kinds(prey, living))
            actions = self.controller.decide(observations, self.rng.controller)
        self.last_decision = Decision(observations, actions, max_turns, thought)

        # 4. Move, then write the results back to each organism. tolist() hands back plain
        #    Python floats with the same values; it is many times faster than converting one
        #    NumPy scalar at a time.
        moved = move(positions, headings, actions, speeds, max_turns, self.world)
        xs, ys = moved.positions[:, 0].tolist(), moved.positions[:, 1].tolist()
        for org, x, y, heading in zip(living, xs, ys, moved.headings.tolist(), strict=True):
            org.x, org.y, org.heading = x, y, heading

        # 2-4 for predators. They act on the same start-of-tick snapshot as the prey (``pred``
        # was taken in step 2, and ``positions`` holds the prey where they were before
        # moving), so it doesn't matter that their turn is written after the prey's. A
        # predator senses the nearest prey exactly as a prey senses the nearest food, so the
        # food seeker's rule chases prey and a brain's food inputs report prey (D-059).
        if hunting:
            pred_obs = sense_food(
                pred.positions, pred.headings, pred.sense_ranges, pred.energies, positions
            )
            pred_thought = None
            if self._neural_predators and hunters:
                pred_obs = replace(
                    pred_obs,
                    body=BodySenses(
                        wall_distance=wall_distance_ahead(
                            pred.positions, pred.headings, self.world.width, self.world.height
                        ),
                        sense_range=pred.sense_ranges,
                        max_turn=pred.max_turns,
                        reproduction_threshold=pred.thresholds,
                    ),
                )
                pred_thought = self.predator_controller.think(
                    pred_obs, self.predator_rng.controller,
                    BrainStack.of([o.brain for o in hunters]),
                )  # fmt: skip
                pred_actions = pred_thought.actions
            else:
                pred_actions = self.predator_controller.decide(
                    pred_obs, self.predator_rng.controller
                )
            self.last_predator_decision = Decision(
                pred_obs, pred_actions, pred.max_turns, pred_thought
            )
            pred_moved = move(
                pred.positions, pred.headings, pred_actions, pred.speeds, pred.max_turns,
                self.world,
            )  # fmt: skip
            pxs, pys = pred_moved.positions[:, 0].tolist(), pred_moved.positions[:, 1].tolist()
            for org, x, y, h in zip(hunters, pxs, pys, pred_moved.headings.tolist(), strict=True):
                org.x, org.y, org.heading = x, y, h

        # 5a. Eat, using post-move positions. Eating is a transfer between the two energy
        #     accounts (food -> organism), so the ledger's in/out totals don't change.
        meals = resolve_feeding(
            moved.positions, self.world.food.positions, self.config.food.eat_radius,
            self.rng.tiebreak,
        )  # fmt: skip
        if self._two_foods:
            # Two foods (06B, D-063): what a meal gives depends on its kind and the eater's
            # diet; the rest of the item's energy leaves through the ledger.
            kinds = self.world.food.kinds[meals.foods].tolist()
            gains, undigested = [], []
            for i, kind in zip(meals.eaters.tolist(), kinds, strict=True):
                living[i].meals_b += kind  # kind is 0 (A) or 1 (B)
                worth = self._digests(living[i])[kind]
                gain = food_value * worth
                gains.append(gain)
                undigested.append(food_value - gain)
            self.ledger.undigested += math.fsum(undigested)
            self.meals_b_this_tick = sum(kinds)
        else:
            gains = [food_value] * len(meals)
        for i, gain in zip(meals.eaters.tolist(), gains, strict=True):
            eater = living[i]
            eater.eat(gain)
            events.append(Event(self.tick, "meal", eater.id, None, gain, eater.x, eater.y, None))
        self.world.food.remove(meals.foods)
        # The working copy gets the same meals: the same addition, so the same value.
        if self._two_foods:
            energies[meals.eaters] += np.array(gains, dtype=np.float64)
        else:
            energies[meals.eaters] += food_value

        # 5a, predators. Capture (6.2, D-058; core/predation.py). After the prey have eaten,
        #     so a prey that reached food this tick is caught with that meal inside it. A caught
        #     prey dies here and does nothing more this tick: it pays no costs, can't reproduce
        #     and doesn't age. Its predator gains capture_efficiency of the prey's energy
        #     (before its own costs, as a prey eats before paying); the rest leaves the system.
        distances = moved.distances
        pred_events: list[Event] = []
        if hunting:
            hunt = self.config.predators
            strikes = resolve_strikes(
                pred_moved.positions, moved.positions, hunt.capture_radius,
                hunt.capture_probability, self.predator_rng.capture,
            )  # fmt: skip
            caught = np.zeros(len(living), dtype=bool)
            losses = []
            struck: list[Strike] = []
            for p, q, hit in zip(
                strikes.predators.tolist(), strikes.prey.tolist(), strikes.caught.tolist(),
                strict=True,
            ):  # fmt: skip
                hunter, victim = hunters[p], living[q]
                held = float(energies[q])  # the prey's energy, this tick's meal included
                if not hit:
                    struck.append(Strike(self.tick, hunter.id, victim.id, False, held, 0.0))
                    continue
                gain = held * hunt.capture_efficiency
                struck.append(Strike(self.tick, hunter.id, victim.id, True, held, gain))
                hunter.eat_prey(gain)
                pred.energies[p] += gain  # the working copy gets the same addition
                losses.append(held - gain)
                caught[q] = True
                # The prey's death names no other organism: events.csv may only refer to this
                # run's organisms (the prey). Who caught whom is the predator's meal event,
                # and captures.csv from 6.4.
                events.append(
                    Event(self.tick, "death", victim.id, None, held, victim.x, victim.y,
                          str(DeathCause.PREDATION))
                )  # fmt: skip
                pred_events.append(
                    Event(self.tick, "meal", hunter.id, victim.id, gain, hunter.x, hunter.y,
                          None)
                )  # fmt: skip
                victim.die(self.tick, DeathCause.PREDATION)
                self.dead.append(victim)
            self.ledger.predation += math.fsum(losses)
            self.strikes_this_tick = struck
            if caught.any():
                # From here on the tick works on the prey still alive. Without predators none
                # of this runs, so prey-only worlds keep exactly their old arrays.
                keep = ~caught
                living = list(compress(living, keep))
                energies, energy_spent = energies[keep], energy_spent[keep]
                metabolic_rates, sense_ranges = metabolic_rates[keep], sense_ranges[keep]
                speeds, thresholds, distances = speeds[keep], thresholds[keep], distances[keep]

        # 5b. Pay costs *after* eating, so a nearly-empty organism that reaches food gets to
        #     eat before its energy hits zero. spend_all() returns what was actually paid, and
        #     that (not the amount requested) is what the ledger records.
        #     Order matters only when energy runs out mid-payment (spending never goes below
        #     zero): metabolism first, then sensing, then movement. See core/costs.py.
        #     Each flow's payments are summed exactly (math.fsum) and added to the ledger once
        #     per tick. Adding millions of small payments one by one to a running total of
        #     ~10^6 loses a sliver to rounding each time, and those slivers add up (D-026).
        costs = living_costs(
            metabolic_rates, sense_ranges, speeds, distances, cfg, self._reference_speed
        )
        paid, energies, energy_spent = spend_all(energies, energy_spent, *costs)
        spent_each = energy_spent.tolist()
        for org, energy, spent in zip(living, energies.tolist(), spent_each, strict=True):
            org.energy, org.energy_spent = energy, spent
        # Predators pay the same three costs at their own rates (their section of the config,
        # their founders' speed for drag). One fsum over both species' payments: fsum is
        # exact, so with no predators each total is what it always was.
        paid_lists = [p.tolist() for p in paid]
        if hunting:
            pred_costs = living_costs(
                pred.metabolic_rates, pred.sense_ranges, pred.speeds, pred_moved.distances,
                self.config.predators, self._predator_reference_speed,
            )  # fmt: skip
            pred_paid, pred_energies, pred_spent = spend_all(
                pred.energies, pred.energy_spent, *pred_costs
            )
            for k in range(3):
                paid_lists[k] += pred_paid[k].tolist()
            pairs = zip(pred_energies.tolist(), pred_spent.tolist(), strict=True)
            for org, (energy, spent) in zip(hunters, pairs, strict=True):
                org.energy, org.energy_spent = energy, spent
        self.ledger.metabolism += math.fsum(paid_lists[0])
        self.ledger.sensing += math.fsum(paid_lists[1])
        self.ledger.movement += math.fsum(paid_lists[2])

        # 6. Deaths: decide for every organism first, then apply. Nobody dies mid-update.
        survivors, dying, lost = self._deaths(living, energies, cfg.max_age, self.dead, events)
        if hunting:
            pred_survivors, pred_dying, pred_lost = self._deaths(
                hunters, pred_energies, self.config.predators.max_age, self.dead_predators,
                pred_events,
            )  # fmt: skip
            lost += pred_lost
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
        # Predators reproduce after the prey, so their newborns' IDs come after the prey
        # newborns': both lists stay in ascending ID order. Their gene changes are kept apart
        # from mutation_log (which is the prey's, mutations.csv) until 6.4 records them.
        if hunting:
            pred_alive = ~pred_dying
            pred_eligible = pred_energies[pred_alive] >= pred.thresholds[pred_alive]
            pred_newborns = self._reproduce(
                pred_survivors, pred_eligible, self._predator_lineage, self.predator_mutation_log
            )
            self.predators = pred_survivors + pred_newborns
            for child in pred_newborns:
                pred_events.append(
                    Event(self.tick, "birth", child.id, child.parent_id, child.energy, child.x,
                          child.y, None)
                )  # fmt: skip
            self.predator_events_this_tick = pred_events

        # 8. Check conservation, then record. A failed check raises EnergyLedgerError.
        self.ledger.check(self.energy_stock(), self.tick)
        population = self.organisms
        summary = TickSummary(
            tick=self.tick,
            population=len(population),
            births=len(newborns),
            deaths=started - len(survivors),  # caught prey included
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
        if hunting:
            now = self.predators
            self.predator_summary = PredatorSummary(
                tick=self.tick,
                population=len(now),
                births=len(pred_newborns),
                deaths=len(hunters) - len(pred_survivors),
                mean_energy=float(np.mean([o.energy for o in now])) if now else math.nan,
                lineages=len({o.founder_id for o in now}),  # counted, never iterated
                attempts=strikes.attempts,
                captures=strikes.captures,
            )

        # 9. Advance time. Newborns stay at age 0: they have not lived through a tick yet.
        for org in survivors:
            org.age += 1
        if hunting:
            for org in pred_survivors:
                org.age += 1
        self.tick += 1
        return summary

    def _deaths(
        self,
        living: list[Organism],
        energies: NDArray[np.float64],
        max_age: int | None,
        graveyard: list[Organism],
        events: list[Event],
    ) -> tuple[list[Organism], NDArray[np.bool_], list[float]]:
        """Tick step 6 for one species: who dies, applied after everyone has been decided.

        Same rule as Organism.cause_of_death: starvation first, then old age. Returns the
        survivors, the mask of who died, and the energy each dead organism still held, which
        leaves the system (D-011); the caller adds it to the ledger.
        """
        starved = energies <= 0.0
        dying = starved
        if max_age is not None:
            ages = np.array([o.age for o in living], dtype=np.int64)
            dying = starved | (ages >= max_age)
        survivors = list(compress(living, ~dying))
        lost = []
        for i in np.flatnonzero(dying).tolist():
            org = living[i]
            cause = DeathCause.STARVATION if starved[i] else DeathCause.OLD_AGE
            # The organism's own record keeps the value, so analysis can see what it died with.
            lost.append(org.energy)
            events.append(
                Event(self.tick, "death", org.id, None, org.energy, org.x, org.y, str(cause))
            )
            org.die(self.tick, cause)
            graveyard.append(org)
        return survivors, dying, lost

    def _reproduce(
        self,
        candidates: list[Organism],
        eligible: NDArray[np.bool_] | None = None,
        lineage: Lineage | None = None,
        log: list[MutationEvent] | None = None,
    ) -> list[Organism]:
        """Create this tick's offspring. Each eligible organism has at most one child.

        ``eligible[i]`` says whether ``candidates[i]`` may reproduce; when omitted it is read
        from each organism (``can_reproduce``). ``lineage`` says which species' settings and
        streams to use, and ``log`` where its gene changes go (default: the prey's).
        """
        species = self._prey if lineage is None else lineage
        log = self.mutation_log if log is None else log
        cfg = species.body
        if not cfg.births:
            return []  # a test arena: nobody is born (D-062); nothing is drawn
        if eligible is None:
            eligible = np.array([o.can_reproduce for o in candidates], dtype=bool)
        room = cfg.max_population - len(candidates)
        chosen = select_parents(eligible, room, species.reproduction)
        if len(chosen) == 0:
            return []

        parents = [candidates[i] for i in chosen]
        positions, headings = place_offspring(
            np.array([[p.x, p.y] for p in parents], dtype=np.float64),
            np.array([p.traits.speed for p in parents], dtype=np.float64),
            self.world,
            species.reproduction,
        )
        newborns = []
        for parent, (x, y), heading in zip(parents, positions, headings, strict=True):
            parent.pay_for_offspring(cfg.offspring_energy, cfg.reproduction_overhead)

            # Inheritance. With mutation disabled, mutate() returns the parent's own genome
            # and draws nothing, which is exactly Milestone 1's behaviour.
            genome, changes = mutate(
                parent.genome, species.genome, self.config.mutation, species.mutation
            )
            # Unchanged genome: reuse the parent's traits (identical, and frozen).
            traits = parent.traits if genome is parent.genome else express(genome, species.genome)
            # The brain is inherited the same way, from its own stream (D-041). Its changes
            # are not logged in mutation_log, which is about the named genes; 4.5 records
            # every brain at birth instead. Mutation disabled: the parent's brain, unchanged.
            brain = parent.brain
            if brain is not None and self.config.mutation.enabled:
                brain, _ = mutate_brain(brain, species.brain, species.brain_rng)
            # The diet (two foods, D-063): the same mutation rule as genes, from the
            # resources stream. Predators have none.
            diet = parent.diet
            if diet is not None:
                diet = mutate_value(
                    diet, self.config.resources.diet, self.config.mutation, self.rng.resources
                )
            child_id = self._new_id()
            for change in changes:
                log.append(
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
                    diet=diet,
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
        """Total energy currently in the system: living organisms (both species) plus uneaten
        food."""
        # Predators' energy counts too. fsum is exact, so adding an empty list changes nothing.
        in_organisms = math.fsum(o.energy for o in [*self.organisms, *self.predators])
        return in_organisms + self.world.food.count * self.config.food.energy_value

    def state_digest(self) -> str:
        """A SHA-256 fingerprint of the full simulation state.

        Two simulations have the same digest only if every food position and every organism's
        id, position, heading, energy, age, alive status and genes match bit for bit. Used to
        check determinism, and recorded in run metadata.

        Genes are included because some never affect behaviour: two runs differing only in a
        neutral marker would otherwise look identical forever. Brain weights are included for
        organisms that have one; organisms without a brain add nothing, so digests of
        rule-based runs are unchanged by Milestone 4. Predators (living, then dead) follow the
        prey in the same form, so a world without them has the digest it always had.
        """
        h = hashlib.sha256()
        h.update(np.int64(self.tick).tobytes())
        h.update(np.ascontiguousarray(self.world.food.positions).tobytes())
        if self._two_foods:  # with one food, kinds are all A and add nothing
            h.update(np.ascontiguousarray(self.world.food.kinds).tobytes())
        # Predators come after the prey (and add nothing when there are none).
        everyone = [*self.organisms, *self.dead, *self.predators, *self.dead_predators]
        for org in everyone:
            genes = list(org.genome.as_dict().values())
            h.update(
                np.array(
                    [org.id, org.x, org.y, org.heading, org.energy, org.age, org.alive, *genes],
                    dtype=np.float64,
                ).tobytes()
            )
            if org.brain is not None:
                h.update(org.brain.to_vector().tobytes())
            if org.diet is not None:
                h.update(np.float64(org.diet).tobytes())
        return h.hexdigest()

    def _sense_kinds(self, prey: Bodies, living: list[Organism]) -> KindSenses:
        """Two foods: each organism's nearest item of each kind, found by the same code as
        the nearest food, and what each kind is worth to it (D-063)."""
        food = self.world.food
        a = sense_food(prey.positions, prey.headings, prey.sense_ranges, prey.energies,
                       food.positions[food.kinds == 0])  # fmt: skip
        b = sense_food(prey.positions, prey.headings, prey.sense_ranges, prey.energies,
                       food.positions[food.kinds == 1])  # fmt: skip
        worth = np.array([self._digests(o) for o in living], dtype=np.float64).reshape(-1, 2)
        return KindSenses(
            a.food_found, a.food_distance, a.food_bearing,
            b.food_found, b.food_distance, b.food_bearing,
            worth[:, 0], worth[:, 1],
        )  # fmt: skip

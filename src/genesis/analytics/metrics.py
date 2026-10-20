"""Metrics: flat, table-shaped records of what happened in a run.

Everything here only *reads* simulation state (the read-only rule in docs/architecture.md).
Rows are plain dicts with a fixed column order, so they can go straight into CSV now and
into Parquet / pandas in Milestone 3.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from genesis.core.organism import Organism, Traits
from genesis.core.simulation import (
    MutationEvent,
    PredatorSummary,
    Simulation,
    Strike,
    TickSummary,
)
from genesis.evolution.genome import gene_names
from genesis.intelligence.brain_inputs import PREY_INPUT_NAMES, parameter_names

TICK_FIELDS: list[str] = [f.name for f in fields(TickSummary)]

# Traits are flattened into prefixed columns (trait_speed, ...), so the organism table stays
# one value per cell. Adding a trait to Traits adds a column automatically.
TRAIT_FIELDS: list[str] = [f"trait_{f.name}" for f in fields(Traits)]

# Genotype columns (gene_*) sit beside phenotype columns (trait_*). They agree for expressed
# genes; gene_neutral_marker has no trait column because it is never expressed.
GENE_FIELDS: list[str] = [f"gene_{name}" for name in gene_names()]

MUTATION_FIELDS: list[str] = [f.name for f in fields(MutationEvent)]

ORGANISM_FIELDS: list[str] = [
    "id",
    "parent_id",
    "founder_id",
    "generation",
    "birth_tick",
    "death_tick",
    "death_cause",
    "alive",
    "age",
    "final_energy",
    "food_eaten",
    "energy_gained",
    "energy_spent",
    "energy_invested",
    "offspring_count",
    *GENE_FIELDS,
    *TRAIT_FIELDS,
]


# brains.csv: one row per organism that had a brain, its 62 parameters by name (D-043).
BRAIN_FIELDS: list[str] = ["id", *parameter_names()]
# In a world with predators, prey brains have 80 parameters, the last 18 their weights on the
# three predator inputs (D-059).
PREY_BRAIN_FIELDS: list[str] = ["id", *parameter_names(PREY_INPUT_NAMES)]


# --- Predator worlds (6.4, D-060): files written only when the config has predators ---------

# predator_ticks.csv: the predators' side of ticks.csv, one row per recorded tick.
PREDATOR_TICK_FIELDS: list[str] = [f.name for f in fields(PredatorSummary)]
PREDATOR_FLOW_FIELDS: tuple[str, ...] = ("births", "deaths", "attempts", "captures")
# predators.csv: organisms.csv's columns, with prey caught where prey count food eaten.
PREDATOR_FIELDS: list[str] = [
    "prey_eaten" if name == "food_eaten" else name for name in ORGANISM_FIELDS
]
# predator_brains.csv: as brains.csv; predators' brains have the standard 62 parameters.
PREDATOR_BRAIN_FIELDS: list[str] = BRAIN_FIELDS
# strikes.csv: every strike, caught or not, in the order they happened.
STRIKE_FIELDS: list[str] = [f.name for f in fields(Strike)]


def predator_tick_row(summary: PredatorSummary) -> dict:
    return {name: getattr(summary, name) for name in PREDATOR_TICK_FIELDS}


def predator_rows(sim: Simulation) -> list[dict]:
    """One row per predator that ever lived, in ascending ID order."""
    everyone = sorted([*sim.predators, *sim.dead_predators], key=lambda o: o.id)
    rows = []
    for o in everyone:
        row = organism_row(o)
        del row["food_eaten"]
        rows.append({name: (o.prey_eaten if name == "prey_eaten" else row[name])
                     for name in PREDATOR_FIELDS})  # fmt: skip
    return rows


def predator_brain_rows(sim: Simulation) -> list[dict]:
    everyone = sorted([*sim.predators, *sim.dead_predators], key=lambda o: o.id)
    names = PREDATOR_BRAIN_FIELDS[1:]
    return [
        {"id": o.id, **dict(zip(names, o.brain.to_vector().tolist(), strict=True))}
        for o in everyone
        if o.brain is not None
    ]


def brain_fields(sim: Simulation) -> list[str]:
    """brains.csv's columns for this run's prey brains."""
    return PREY_BRAIN_FIELDS if sim.config.predators is not None else BRAIN_FIELDS


def tick_row(summary: TickSummary) -> dict:
    # Same dict as dataclasses.asdict(summary), without its deep copy of every value, which
    # cost more per tick than recording everything else (D-038).
    return {name: getattr(summary, name) for name in TICK_FIELDS}


def organism_row(org: Organism) -> dict:
    row = {
        "id": org.id,
        "parent_id": org.parent_id,
        "founder_id": org.founder_id,
        "generation": org.generation,
        "birth_tick": org.birth_tick,
        "death_tick": org.death_tick,
        # str() so the CSV holds "starvation", not "DeathCause.STARVATION".
        "death_cause": None if org.death_cause is None else str(org.death_cause),
        "alive": org.alive,
        "age": org.age,
        "final_energy": org.energy,  # current energy if alive; energy held at death if dead
        "food_eaten": org.food_eaten,
        "energy_gained": org.energy_gained,
        "energy_spent": org.energy_spent,
        "energy_invested": org.energy_invested,
        "offspring_count": org.offspring_count,
    }
    row.update({f"gene_{name}": value for name, value in org.genome.as_dict().items()})
    row.update({f"trait_{name}": value for name, value in asdict(org.traits).items()})
    return row


def organism_rows(sim: Simulation) -> list[dict]:
    """One row per organism that ever lived, living and dead, in ascending ID order."""
    everyone = sorted([*sim.organisms, *sim.dead], key=lambda o: o.id)
    return [organism_row(o) for o in everyone]


def brain_rows(sim: Simulation) -> list[dict]:
    """One row per organism that ever had a brain, in ascending ID order (none without
    brains). Brains never change during a lifetime, so one row per organism is complete."""
    everyone = sorted([*sim.organisms, *sim.dead], key=lambda o: o.id)
    names = brain_fields(sim)[1:]
    return [
        {"id": o.id, **dict(zip(names, o.brain.to_vector().tolist(), strict=True))}
        for o in everyone
        if o.brain is not None
    ]


def mutation_rows(sim: Simulation) -> list[dict]:
    """One row per gene change, in the order the mutations happened."""
    return [asdict(event) for event in sim.mutation_log]

"""Metrics: flat, table-shaped records of what happened in a run.

Everything here only *reads* simulation state (the read-only rule in docs/architecture.md).
Rows are plain dicts with a fixed column order, so they can go straight into CSV now and
into Parquet / pandas in Milestone 3.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from genesis.core.organism import Organism, Traits
from genesis.core.simulation import MutationEvent, Simulation, TickSummary
from genesis.evolution.genome import gene_names

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


def mutation_rows(sim: Simulation) -> list[dict]:
    """One row per gene change, in the order the mutations happened."""
    return [asdict(event) for event in sim.mutation_log]

"""Table definitions: docs/data-dictionary.md as code.

Each table has a pyarrow schema (column names and types, in order) and a primary key. The
ETL converts every CSV to exactly this schema, so a Parquet file in the lake always matches
the dictionary, whichever version of the code wrote the original run folder.

Type mapping (DuckDB name -> Arrow type): INTEGER -> int32, DOUBLE -> float64,
BOOLEAN -> bool, VARCHAR -> string, TIMESTAMP -> timestamp in microseconds, UTC. The run's
config is stored as JSON text; DuckDB views read it with its JSON functions.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

from genesis.evolution.genome import gene_names
from genesis.intelligence.brain_inputs import PREY_INPUT_NAMES, parameter_names

INT, FLOAT, BOOL, TEXT = pa.int32(), pa.float64(), pa.bool_(), pa.string()
# Microseconds: Parquet has no whole-second timestamp type (it would silently widen "s" to
# "ms"), and microseconds are DuckDB's own TIMESTAMP precision.
TIMESTAMP = pa.timestamp("us", tz="UTC")

GENE_COLUMNS = [f"gene_{g}" for g in gene_names()]
TRAIT_COLUMNS = [f"trait_{g}" for g in gene_names() if g != "neutral_marker"]
BASE_BRAIN_COLUMNS = parameter_names()  # wh_0_food_seen, ..., bo_throttle (62)
# Prey in worlds with predators have 18 more weights, on their three predator inputs (D-059).
# Appended after the 62, so the table keeps its old columns in their old order; older runs
# have them empty (NULL).
THREAT_BRAIN_COLUMNS = [
    c for c in parameter_names(PREY_INPUT_NAMES) if c not in set(BASE_BRAIN_COLUMNS)
]
BRAIN_COLUMNS = [*BASE_BRAIN_COLUMNS, *THREAT_BRAIN_COLUMNS]


@dataclass(frozen=True)
class Table:
    name: str
    schema: pa.Schema
    primary_key: tuple[str, ...]
    csv_file: str | None  # source file in a run folder (None: built from run.json)
    since_version: int  # first run-folder schema version that has this table
    renames: tuple[tuple[str, str], ...] = ()  # CSV column -> table column
    predators_only: bool = False  # written only by worlds with predators (D-060)


def _schema(*columns: tuple[str, pa.DataType]) -> pa.Schema:
    return pa.schema([pa.field(name, kind) for name, kind in columns])


RUNS = Table(
    "runs",
    _schema(
        ("run_id", TEXT),
        ("experiment_id", TEXT),
        ("condition", TEXT),
        ("condition_derived", BOOL),
        ("seed", INT),
        ("status", TEXT),
        ("schema_version", INT),
        ("config_hash", TEXT),
        ("config", TEXT),
        ("git_commit", TEXT),
        ("git_dirty", BOOL),
        ("python_version", TEXT),
        ("numpy_version", TEXT),
        ("platform", TEXT),
        ("machine", TEXT),
        ("started_at", TIMESTAMP),
        ("finished_at", TIMESTAMP),
        ("duration_seconds", FLOAT),
        ("ticks_run", INT),
        ("stop_reason", TEXT),
        ("final_population", INT),
        ("organisms_ever", INT),
        ("mutations", INT),
        ("final_state_digest", TEXT),
        ("failed_at_tick", INT),
        ("error", TEXT),
        ("ticks_every", INT),
        ("events_recorded", TEXT),
        ("final_predators", INT),  # worlds with predators only (6.4)
        ("predators_ever", INT),
    ),
    ("run_id",),
    None,
    1,
)

TICKS = Table(
    "ticks",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("population", INT),
        ("births", INT),
        ("deaths", INT),
        ("food_count", INT),
        ("food_spawned", INT),
        ("food_eaten", INT),
        ("mean_energy", FLOAT),
        ("lineages", INT),
        ("mutations", INT),
    ),
    ("run_id", "tick"),
    "ticks.csv",
    1,
)

GENE_STATS = Table(
    "gene_stats",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("gene", TEXT),
        ("n", INT),
        ("mean", FLOAT),
        ("sd", FLOAT),
        ("min", FLOAT),
        ("max", FLOAT),
    ),
    ("run_id", "tick", "gene"),
    "gene_stats.csv",
    2,
)

GENOMES = Table(
    "genomes",
    _schema(
        ("run_id", TEXT), ("tick", INT), ("organism_id", INT), *[(c, FLOAT) for c in GENE_COLUMNS]
    ),
    ("run_id", "tick", "organism_id"),
    "genomes.csv",
    2,
    renames=(("id", "organism_id"),),
)

ORGANISMS = Table(
    "organisms",
    _schema(
        ("run_id", TEXT),
        ("organism_id", INT),
        ("parent_id", INT),
        ("founder_id", INT),
        ("generation", INT),
        ("birth_tick", INT),
        ("death_tick", INT),
        ("death_cause", TEXT),
        ("alive", BOOL),
        ("age", INT),
        ("final_energy", FLOAT),
        ("food_eaten", INT),
        ("energy_gained", FLOAT),
        ("energy_spent", FLOAT),
        ("energy_invested", FLOAT),
        ("offspring_count", INT),
        *[(c, FLOAT) for c in GENE_COLUMNS],
        *[(c, FLOAT) for c in TRAIT_COLUMNS],
    ),
    ("run_id", "organism_id"),
    "organisms.csv",
    1,
    renames=(("id", "organism_id"),),
)

MUTATIONS = Table(
    "mutations",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("parent_id", INT),
        ("child_id", INT),
        ("gene", TEXT),
        ("before", FLOAT),
        ("after", FLOAT),
    ),
    ("run_id", "child_id", "gene"),
    "mutations.csv",
    2,
)

EVENTS = Table(
    "events",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("seq", INT),
        ("kind", TEXT),
        ("organism_id", INT),
        ("other_id", INT),
        ("energy", FLOAT),
        ("x", FLOAT),
        ("y", FLOAT),
        ("detail", TEXT),
    ),
    ("run_id", "tick", "seq"),
    "events.csv",
    3,
)

BEHAVIOUR = Table(
    "behaviour",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("n", INT),
        ("seeing_food", INT),
        ("toward_food", FLOAT),
        ("mean_turn", FLOAT),
        ("mean_throttle", FLOAT),
        ("weight_sd", FLOAT),
        ("weight_drift", FLOAT),
    ),
    ("run_id", "tick"),
    "behaviour.csv",
    4,
)

BRAINS = Table(
    "brains",
    _schema(("run_id", TEXT), ("organism_id", INT), *[(c, FLOAT) for c in BRAIN_COLUMNS]),
    ("run_id", "organism_id"),
    "brains.csv",
    4,
    renames=(("id", "organism_id"),),
)

# --- Worlds with predators (6.4, D-060) ------------------------------------------------------

PREDATOR_TICKS = Table(
    "predator_ticks",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("population", INT),
        ("births", INT),
        ("deaths", INT),
        ("mean_energy", FLOAT),
        ("lineages", INT),
        ("attempts", INT),
        ("captures", INT),
    ),
    ("run_id", "tick"),
    "predator_ticks.csv",
    5,
    predators_only=True,
)

PREDATORS = Table(
    "predators",
    _schema(
        *[
            ("predator_id", INT) if f.name == "organism_id"
            else ("prey_eaten", INT) if f.name == "food_eaten"
            else (f.name, f.type)
            for f in ORGANISMS.schema
        ]
    ),
    ("run_id", "predator_id"),
    "predators.csv",
    5,
    renames=(("id", "predator_id"),),
    predators_only=True,
)  # fmt: skip

PREDATOR_BRAINS = Table(
    "predator_brains",
    _schema(("run_id", TEXT), ("predator_id", INT), *[(c, FLOAT) for c in BASE_BRAIN_COLUMNS]),
    ("run_id", "predator_id"),
    "predator_brains.csv",
    5,
    renames=(("id", "predator_id"),),
    predators_only=True,
)

STRIKES = Table(
    "strikes",
    _schema(
        ("run_id", TEXT),
        ("tick", INT),
        ("predator_id", INT),
        ("prey_id", INT),
        ("caught", BOOL),
        ("prey_energy", FLOAT),
        ("predator_gain", FLOAT),
    ),
    ("run_id", "tick", "predator_id"),  # one strike per predator per tick
    "strikes.csv",
    5,
    predators_only=True,
)

DATA_TABLES = [TICKS, GENE_STATS, GENOMES, ORGANISMS, MUTATIONS, EVENTS, BEHAVIOUR, BRAINS,
               PREDATOR_TICKS, PREDATORS, PREDATOR_BRAINS, STRIKES]  # fmt: skip
ALL_TABLES = [RUNS, *DATA_TABLES]

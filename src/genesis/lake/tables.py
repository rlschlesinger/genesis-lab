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

INT, FLOAT, BOOL, TEXT = pa.int32(), pa.float64(), pa.bool_(), pa.string()
# Microseconds: Parquet has no whole-second timestamp type (it would silently widen "s" to
# "ms"), and microseconds are DuckDB's own TIMESTAMP precision.
TIMESTAMP = pa.timestamp("us", tz="UTC")

GENE_COLUMNS = [f"gene_{g}" for g in gene_names()]
TRAIT_COLUMNS = [f"trait_{g}" for g in gene_names() if g != "neutral_marker"]


@dataclass(frozen=True)
class Table:
    name: str
    schema: pa.Schema
    primary_key: tuple[str, ...]
    csv_file: str | None  # source file in a run folder (None: built from run.json)
    since_version: int  # first run-folder schema version that has this table
    renames: tuple[tuple[str, str], ...] = ()  # CSV column -> table column


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

DATA_TABLES = [TICKS, GENE_STATS, GENOMES, ORGANISMS, MUTATIONS, EVENTS]
ALL_TABLES = [RUNS, *DATA_TABLES]

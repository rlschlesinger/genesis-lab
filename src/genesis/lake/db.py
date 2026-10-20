"""DuckDB over the lake: views (saved queries) that read the Parquet files directly.

``connect()`` returns an in-memory DuckDB connection with every view defined. Views store no
data, so creating them is instant and they always reflect the current lake. ``rebuild_db``
writes the same views into a database file for other tools (DuckDB CLI, DBeaver, ...); that
file uses absolute paths, so rebuild it if the project folder moves.

Views and macros (docs/schema.md):

    runs, ticks, gene_stats, genomes, organisms, mutations, events,
    behaviour, brains, predator_ticks, predators, predator_brains,
    strikes                                                           one per lake table
    experiments          built from docs/experiments/*.md
    completed_runs       runs WHERE status = 'completed' (start analyses here)
    run_params           common config values as plain columns
    lineage_sizes        per run and founder: descendants born, alive at the end
    species_counts       per run and recorded tick: prey and predators side by side
    settled_gene_means(first_tick, last_tick)   per run and gene: mean over a window
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import duckdb
import pyarrow as pa

from genesis.lake.ingest import DEFAULT_LAKE
from genesis.lake.tables import ALL_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DOCS = PROJECT_ROOT / "docs" / "experiments"
DEFAULT_DB = Path("data") / "genesis.duckdb"

DUCKDB_TYPES = {
    pa.int32(): "INTEGER",
    pa.float64(): "DOUBLE",
    pa.bool_(): "BOOLEAN",
    pa.string(): "VARCHAR",
    pa.timestamp("us", tz="UTC"): "TIMESTAMPTZ",
}

DERIVED_VIEWS = """
CREATE OR REPLACE VIEW completed_runs AS
SELECT * FROM runs WHERE status = 'completed';

CREATE OR REPLACE VIEW run_params AS
SELECT
    run_id, experiment_id, condition, seed, status,
    config ->> '$.organisms.controller'                          AS controller,
    (config ->> '$.food.regrowth_per_tick')::DOUBLE               AS food_regrowth,
    (config ->> '$.organisms.initial_count')::INTEGER             AS initial_count,
    (config ->> '$.run.max_ticks')::INTEGER                       AS max_ticks,
    (config ->> '$.mutation.enabled')::BOOLEAN                    AS mutation_enabled,
    (config ->> '$.mutation.rate')::DOUBLE                        AS mutation_rate,
    (config ->> '$.mutation.size')::DOUBLE                        AS mutation_size,
    (config ->> '$.organisms.speed_cost_exponent')::DOUBLE        AS speed_cost_exponent,
    (config ->> '$.organisms.sense_cost_per_unit')::DOUBLE        AS sense_cost_per_unit,
    (config -> '$.brain') IS NOT NULL                             AS has_brains,
    (config ->> '$.brain.mutation_rate')::DOUBLE                  AS brain_mutation_rate,
    (config ->> '$.brain.mutation_size')::DOUBLE                  AS brain_mutation_size,
    (config -> '$.predators') IS NOT NULL                         AS has_predators,
    (config ->> '$.predators.initial_count')::INTEGER             AS initial_predators,
    config ->> '$.predators.controller'                           AS predator_controller
FROM runs;

CREATE OR REPLACE VIEW species_counts AS
SELECT
    t.run_id, t.tick,
    t.population                   AS prey,
    p.population                   AS predators,
    p.attempts, p.captures,
    t.deaths                       AS prey_deaths
FROM ticks AS t JOIN predator_ticks AS p USING (run_id, tick);

CREATE OR REPLACE VIEW lineage_sizes AS
SELECT
    run_id,
    founder_id,
    count(*)                       AS born,
    count(*) FILTER (WHERE alive)  AS alive_at_end
FROM organisms
GROUP BY run_id, founder_id;

CREATE OR REPLACE MACRO settled_gene_means(first_tick, last_tick) AS TABLE
SELECT
    run_id,
    gene,
    avg(mean)                      AS settled_mean,
    count(*)                       AS rows_in_window,
    count(mean)                    AS rows_with_population
FROM gene_stats
WHERE tick BETWEEN first_tick AND last_tick
GROUP BY run_id, gene;
"""


def connect(lake: str | Path = DEFAULT_LAKE) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with every view and macro defined over ``lake``."""
    con = duckdb.connect()
    define_views(con, Path(lake))
    return con


def define_views(con: duckdb.DuckDBPyConnection, lake: Path) -> None:
    for spec in ALL_TABLES:
        folder = lake / spec.name
        if any(folder.glob("*.parquet")):
            pattern = (folder.resolve() / "*.parquet").as_posix()
            source = _aligned(con, spec.schema, pattern)
        else:
            source = _empty_select(spec.schema)  # e.g. no run has logged events yet
        if spec.name == "runs":
            # The config column is JSON text in Parquet; expose it as DuckDB's JSON type.
            source = f"SELECT * REPLACE (config::JSON AS config) FROM ({source})"
        con.execute(f"CREATE OR REPLACE VIEW {spec.name} AS {source}")
    _define_experiments(con)
    con.execute(DERIVED_VIEWS)


def rebuild_db(db_path: str | Path = DEFAULT_DB, lake: str | Path = DEFAULT_LAKE) -> Path:
    """Write the views into a DuckDB database file (replacing it). Returns the path."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    with duckdb.connect(str(db_path)) as con:
        define_views(con, Path(lake))
    return db_path


def _aligned(con: duckdb.DuckDBPyConnection, schema: pa.Schema, pattern: str) -> str:
    """Read every file of a table with exactly the dictionary's columns, in its order.

    A table can gain columns (brains' 18 predator weights and runs' predator counts, 6.4).
    ``union_by_name`` lines up files written before and after by column name; a column no
    file has yet (a lake with only older runs) is still offered, as NULL, so a query naming
    it works on any lake (D-060).
    """
    files = f"read_parquet('{pattern}', union_by_name = true)"
    present = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {files}").fetchall()}
    columns = ", ".join(
        f.name if f.name in present else f"CAST(NULL AS {DUCKDB_TYPES[f.type]}) AS {f.name}"
        for f in schema
    )
    return f"SELECT {columns} FROM {files}"


def _empty_select(schema: pa.Schema) -> str:
    """A query with the table's columns and types but no rows."""
    columns = ", ".join(f"CAST(NULL AS {DUCKDB_TYPES[f.type]}) AS {f.name}" for f in schema)
    return f"SELECT {columns} WHERE false"


def _define_experiments(con: duckdb.DuckDBPyConnection) -> None:
    """One row per experiment document: id, title, path, and the commit that added it."""
    rows = []
    for path in sorted(EXPERIMENT_DOCS.glob("E*.md")):
        experiment_id = path.name.split("-", 1)[0]
        heading = next(
            (line for line in path.read_text().splitlines() if line.startswith("# ")),
            f"# {experiment_id}",
        )
        title = re.sub(r"^#\s*E\d+\s*·\s*", "", heading).lstrip("# ").strip()
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        rows.append((experiment_id, title, relative, _first_commit(relative)))
    con.execute(
        "CREATE OR REPLACE TABLE experiments (experiment_id VARCHAR PRIMARY KEY, title VARCHAR,"
        " definition_path VARCHAR, defined_at_commit VARCHAR)"
    )
    if rows:
        con.executemany("INSERT INTO experiments VALUES (?, ?, ?, ?)", rows)


def _first_commit(relative_path: str) -> str | None:
    """The commit that first added a file: evidence a definition predates its runs."""
    try:
        result = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%h", "--", relative_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commits = result.stdout.split()
    return commits[-1] if commits else None

"""ETL: run folders -> validated Parquet tables in the lake (docs/schema.md).

    extract    read run.json and the CSV files; detect the run-folder schema version
    transform  apply the data dictionary's types; nan -> NULL; id -> organism_id; add run_id;
               derive condition (versions 1-2) and config_hash (when missing)
    load       validate every check; only then write data/lake/<table>/<run_id>.parquet

Run folders are only read, never modified. A run failing any check is refused whole.
Re-ingesting a run replaces its files, so ingesting is safe to repeat.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from genesis.core.config import hash_config_dict
from genesis.lake.tables import DATA_TABLES, RUNS, Table
from genesis.lake.validate import ValidationError, validate_run

DEFAULT_LAKE = Path("data") / "lake"
FOLDER_NAME = re.compile(r"(?P<condition>.+)-s(?P<seed>\d+)")  # e.g. S_plenty-s2000


@dataclass
class IngestResult:
    run_dir: Path
    run_id: str | None
    ingested: bool
    rows: dict[str, int] = field(default_factory=dict)
    reason: str | None = None  # why a run was refused


def find_run_dirs(paths: Iterable[str | Path]) -> list[Path]:
    """Run folders at or below each path (a run folder is one containing run.json)."""
    found: set[Path] = set()
    for path in map(Path, paths):
        if (path / "run.json").exists():
            found.add(path)
        else:
            found.update(p.parent for p in path.rglob("run.json"))
    return sorted(found)


def ingest_paths(paths: Iterable[str | Path], lake: Path = DEFAULT_LAKE) -> list[IngestResult]:
    return [ingest_run(run_dir, lake) for run_dir in find_run_dirs(paths)]


def ingest_run(run_dir: str | Path, lake: Path = DEFAULT_LAKE) -> IngestResult:
    """Extract, transform, validate and load one run folder."""
    run_dir = Path(run_dir)
    try:
        meta = json.loads((run_dir / "run.json").read_text())
        tables = extract_transform(run_dir, meta)
        validate_run(meta, tables)
    except (ValidationError, ValueError, KeyError, OSError, pa.ArrowException) as exc:
        return IngestResult(run_dir, _run_id_or_none(run_dir), False, reason=str(exc))
    _write_all(tables, meta["run_id"], Path(lake))
    return IngestResult(
        run_dir, meta["run_id"], True, {name: t.num_rows for name, t in tables.items()}
    )


# --- Extract and transform ----------------------------------------------------------------


def schema_version(run_dir: Path, meta: dict) -> int:
    """Recorded from version 3 on; inferred for older folders from the files they contain."""
    if "schema_version" in meta:
        return meta["schema_version"]
    return 2 if (run_dir / "gene_stats.csv").exists() else 1


def extract_transform(run_dir: Path, meta: dict) -> dict[str, pa.Table]:
    version = schema_version(run_dir, meta)
    tables = {"runs": runs_row(run_dir, meta, version)}
    if meta["status"] != "completed":
        return tables  # failed or unfinished: a runs row, but no data to load
    for spec in DATA_TABLES:
        if version >= spec.since_version:
            tables[spec.name] = read_table(run_dir / spec.csv_file, spec, meta["run_id"])
    return tables


def runs_row(run_dir: Path, meta: dict, version: int) -> pa.Table:
    condition, derived = meta.get("condition"), False
    if version < 3 and meta.get("experiment_id"):
        # Before version 3 the condition existed only in the folder name.
        match = FOLDER_NAME.fullmatch(run_dir.name)
        if match and int(match["seed"]) == meta["seed"]:
            condition, derived = match["condition"], True
    git, env = meta.get("git") or {}, meta.get("environment") or {}
    row = {
        "run_id": meta["run_id"],
        "experiment_id": meta.get("experiment_id"),
        "condition": condition,
        "condition_derived": derived,
        "seed": meta["seed"],
        "status": meta["status"],
        "schema_version": version,
        "config_hash": meta.get("config_hash") or hash_config_dict(meta["config"]),
        "config": json.dumps(meta["config"], sort_keys=True),
        "git_commit": git.get("commit"),
        "git_dirty": git.get("dirty"),
        "python_version": env.get("python"),
        "numpy_version": (env.get("packages") or {}).get("numpy"),
        "platform": env.get("platform"),
        "machine": env.get("machine"),
        "started_at": _timestamp(meta.get("started_at")),
        "finished_at": _timestamp(meta.get("finished_at")),
        "duration_seconds": meta.get("duration_seconds"),
        "ticks_run": meta.get("ticks_run"),
        "stop_reason": meta.get("stop_reason"),
        "final_population": meta.get("final_population"),
        "organisms_ever": meta.get("organisms_ever"),
        "mutations": meta.get("mutations"),
        "final_state_digest": meta.get("final_state_digest"),
        "failed_at_tick": meta.get("failed_at_tick"),
        "error": meta.get("error"),
        "ticks_every": meta.get("ticks_every", 1),
        "events_recorded": meta.get("events_recorded", ""),
    }
    return pa.Table.from_pylist([row], schema=RUNS.schema)


def read_table(path: Path, spec: Table, run_id: str) -> pa.Table:
    """Read one CSV into exactly the table's schema.

    Types are stated, not guessed, so a column that should be a whole number can never be
    read as text. pyarrow's default null markers include "" and "nan", so empty cells and NaN
    both become NULL. Columns an older run format lacks are added as all-NULL.
    """
    renames = dict(spec.renames)
    source_name = {table_col: csv_col for csv_col, table_col in spec.renames}
    types = {source_name.get(f.name, f.name): f.type for f in spec.schema if f.name != "run_id"}
    try:
        table = pacsv.read_csv(
            path,
            convert_options=pacsv.ConvertOptions(column_types=types, strings_can_be_null=True),
        )
    except pa.ArrowInvalid as exc:
        # pyarrow reports "CSV column #3"; name the file and column so the message is usable.
        message = str(exc)
        match = re.search(r"column #(\d+)", message)
        if match:
            header = path.read_text(encoding="utf-8").partition("\n")[0].split(",")
            message = f"column {header[int(match[1])]!r}: {message}"
        raise ValidationError("types", f"{path.name}, {message}") from exc
    table = table.rename_columns([renames.get(name, name) for name in table.column_names])

    unexpected = set(table.column_names) - set(spec.schema.names)
    if unexpected:
        raise ValidationError("types", f"{path.name} has unexpected columns {sorted(unexpected)}")
    n = table.num_rows
    columns = []
    for f in spec.schema:
        if f.name == "run_id":
            columns.append(pa.array([run_id] * n, type=f.type))
        elif f.name in table.column_names:
            columns.append(table[f.name].cast(f.type))
        else:
            columns.append(pa.nulls(n, type=f.type))  # not in this run-folder version
    return pa.Table.from_arrays(columns, schema=spec.schema)


# --- Load ---------------------------------------------------------------------------------


def _write_all(tables: dict[str, pa.Table], run_id: str, lake: Path) -> None:
    """Write every table to a temporary file first, then rename them all into place.

    A crash mid-way can leave stray .tmp files but never a half-written Parquet file under a
    real name, and nothing is renamed until every table has been written.
    """
    staged = []
    for name, table in tables.items():
        final = lake / name / f"{run_id}.parquet"
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd")
        staged.append((tmp, final))
    for tmp, final in staged:
        os.replace(tmp, final)


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _run_id_or_none(run_dir: Path) -> str | None:
    try:
        return json.loads((run_dir / "run.json").read_text())["run_id"]
    except (OSError, ValueError, KeyError):
        return None

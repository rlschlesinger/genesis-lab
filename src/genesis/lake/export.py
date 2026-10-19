"""Exporting lake data so it can be reloaded and analysed without Genesis Lab.

An experiment export is a folder with one file per table (Parquet or CSV), a README.md that
explains every column (cut from docs/data-dictionary.md, so it can't drift from it) and a
manifest.json with row counts and a SHA-256 checksum per file. Rows are sorted by primary key,
so the same lake always exports the same contents in the same order.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from genesis.analytics.provenance import git_info
from genesis.lake.db import PROJECT_ROOT, connect
from genesis.lake.ingest import DEFAULT_LAKE
from genesis.lake.tables import ALL_TABLES

FORMATS = ("parquet", "csv")
DICTIONARY = PROJECT_ROOT / "docs" / "data-dictionary.md"


def export_experiment(
    experiment_id: str,
    out_dir: str | Path,
    fmt: str = "parquet",
    tables: list[str] | None = None,
    lake: str | Path = DEFAULT_LAKE,
) -> dict:
    """Write one experiment's tables to ``out_dir``. Returns the manifest."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}, got {fmt!r}")
    known = [t.name for t in ALL_TABLES]
    tables = tables or known
    unknown = set(tables) - set(known)
    if unknown:
        raise ValueError(f"unknown table(s) {sorted(unknown)}; choose from {known}")

    con = connect(lake)
    run_count = con.execute(
        "SELECT count(*) FROM runs WHERE experiment_id = ?", [experiment_id]
    ).fetchone()[0]
    if run_count == 0:
        raise ValueError(f"no runs of {experiment_id} in the lake")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for spec in ALL_TABLES:
        if spec.name not in tables:
            continue
        path = out / f"{spec.name}.{fmt}"
        select = _select(spec.name, spec.schema.names)
        query = (
            f"SELECT {select} FROM {spec.name} WHERE run_id IN (SELECT run_id FROM runs "
            f"WHERE experiment_id = $e) ORDER BY {', '.join(spec.primary_key)}"
        )
        rows = con.execute(f"SELECT count(*) FROM ({query})", {"e": experiment_id}).fetchone()[0]
        if rows == 0 and spec.name != "runs":
            continue  # e.g. no events logged: no empty file
        _copy(con, query, path, fmt, {"e": experiment_id})
        files[path.name] = {"table": spec.name, "rows": rows, "sha256": _sha256(path)}

    manifest = {
        "experiment_id": experiment_id,
        "format": fmt,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_commit": git_info(),
        "runs": run_count,
        "files": files,
        "notes": "Rows sorted by primary key. NULL = no value. One row per run in runs.* "
        "(failed runs included, status column); data tables hold completed runs only.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "README.md").write_text(readme(experiment_id, [f["table"] for f in files.values()]))
    return manifest


def export_query(sql: str, out_path: str | Path, lake: str | Path = DEFAULT_LAKE) -> int:
    """Write any query's result to a .parquet or .csv file. Returns the row count."""
    out = Path(out_path)
    fmt = out.suffix.lstrip(".").lower()
    if fmt not in FORMATS:
        raise ValueError("output file must end in .parquet or .csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    con = connect(lake)
    _copy(con, sql, out, fmt, {})
    return con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]


def verify_export(out_dir: str | Path) -> list[str]:
    """Problems found when checking an export against its manifest (empty list = intact)."""
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text())
    problems = []
    for name, info in manifest["files"].items():
        path = out / name
        if not path.exists():
            problems.append(f"{name} is missing")
        elif _sha256(path) != info["sha256"]:
            problems.append(f"{name} does not match its checksum (changed or truncated)")
    return problems


def readme(experiment_id: str, tables: list[str]) -> str:
    """The data dictionary's conventions plus the sections for the exported tables."""
    text = DICTIONARY.read_text()
    conventions = text.split("\n---\n", 1)[0].split("**Conventions**", 1)[-1]
    sections = re.split(r"\n(?=## `)", text)
    chosen = [
        s.strip() for s in sections if (m := re.match(r"## `(\w+)`", s)) and m.group(1) in tables
    ]
    return (
        f"# {experiment_id} export from Genesis Lab\n\n"
        "Files: one per table below, plus `manifest.json` (row counts, SHA-256 checksums, "
        "source commit). Check integrity by recomputing each file's SHA-256.\n\n"
        "Each **run** is one independent replicate; organisms within a run are not. Join "
        "tables on `run_id` (and `organism_id` or `tick` where relevant) — always including "
        "`run_id`, since organism and tick numbers repeat across runs.\n\n"
        f"## Conventions\n{conventions}\n" + "\n\n".join(chosen) + "\n"
    )


def _select(table: str, columns: list[str]) -> str:
    # The runs view exposes config as JSON; export it as plain text for any reader.
    return ", ".join(
        "config::VARCHAR AS config" if table == "runs" and c == "config" else c for c in columns
    )


def _copy(con, query: str, path: Path, fmt: str, params: dict) -> None:
    options = "FORMAT parquet, COMPRESSION zstd" if fmt == "parquet" else "FORMAT csv, HEADER"
    con.execute(f"COPY ({query}) TO '{path.as_posix()}' ({options})", params)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

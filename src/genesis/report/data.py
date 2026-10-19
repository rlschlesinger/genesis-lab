"""Loading a recorded run for reporting. Reads files only; never runs a simulation.

Because the report depends only on what was recorded, any past run can be re-plotted, and a
chart can never show something the data files don't contain.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FILES = ["run.json", "ticks.csv", "gene_stats.csv", "genomes.csv", "mutations.csv"]
MAX_POINTS = 2000  # per plotted line; the CSVs keep every tick


@dataclass(frozen=True, slots=True)
class GeneBounds:
    initial: float
    min: float
    max: float
    mutable: bool


@dataclass(frozen=True, slots=True)
class RunData:
    run_dir: Path
    meta: dict
    ticks: list[dict]  # columns as written; numbers parsed
    gene_stats: dict[str, list[dict]]  # gene -> rows in tick order
    genomes: list[dict]
    mutations: list[dict]
    bounds: dict[str, GeneBounds]  # gene -> limits, from the run's own recorded config

    @property
    def genes(self) -> list[str]:
        return list(self.bounds)


def load_run(run_dir: str | Path) -> RunData:
    run_dir = Path(run_dir)
    missing = [name for name in REQUIRED_FILES if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"{run_dir} is missing {', '.join(missing)}; is it a run folder?")
    meta = json.loads((run_dir / "run.json").read_text())
    if meta.get("status") != "completed":
        raise ValueError(f"{run_dir}: run status is {meta.get('status')!r}, not 'completed'")

    gene_stats: dict[str, list[dict]] = {}
    for row in _read(run_dir / "gene_stats.csv"):
        gene_stats.setdefault(row["gene"], []).append(row)

    # Bounds come from the config recorded in run.json, so the report always describes the
    # run as it actually was, even if configs/ has changed since.
    bounds = {
        gene: GeneBounds(spec["initial"], spec["min"], spec["max"], spec.get("mutable", True))
        for gene, spec in meta["config"]["genome"].items()
    }
    return RunData(
        run_dir=run_dir,
        meta=meta,
        ticks=_read(run_dir / "ticks.csv"),
        gene_stats=gene_stats,
        genomes=_read(run_dir / "genomes.csv"),
        mutations=_read(run_dir / "mutations.csv"),
        bounds=bounds,
    )


def downsample(rows: list[dict], max_points: int = MAX_POINTS) -> list[dict]:
    """Every k-th row (k chosen so at most ``max_points`` remain), always keeping the last.

    A fixed stride, not random sampling, so the same run always plots the same points.
    """
    if len(rows) <= max_points:
        return rows
    stride = math.ceil(len(rows) / max_points)
    kept = rows[::stride]
    if kept[-1] is not rows[-1]:
        kept.append(rows[-1])
    return kept


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [{k: _number(k, v) for k, v in row.items()} for row in csv.DictReader(f)]


def _number(key: str, value: str):
    """CSV cells are text; turn numeric ones back into numbers. Empty means None."""
    if value == "":
        return None
    if key in {"gene", "death_cause"}:
        return value
    try:
        as_float = float(value)  # also parses "nan"
    except ValueError:
        return value  # e.g. "True" / "False"
    return int(value) if value.lstrip("-").isdigit() else as_float

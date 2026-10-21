"""Helpers for running and measuring pre-registered experiments (docs/experiments/).

An experiment is a set of *conditions* (named config changes) run across a fixed list of
seeds. Every run is recorded with ``execute_run``, and every measurement is taken from the
recorded files, so analyses can be re-run from disk without re-simulating.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, editable_dump


@dataclass(frozen=True)
class Condition:
    """A named set of config changes, as dotted paths: {"food.regrowth_per_tick": 1.0}."""

    label: str
    changes: dict = field(default_factory=dict)


def apply_changes(base: SimulationConfig, changes: dict) -> SimulationConfig:
    """A validated copy of ``base`` with dotted-path changes applied."""
    raw = editable_dump(base)  # every setting present, so any real path can be changed
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        section = raw
        for key in parents:
            # A path through a value that isn't a section ("run.seed.x") is as wrong as a
            # typo: KeyError, not a TypeError from indexing an int or a list.
            if not isinstance(section, dict) or key not in section:
                raise KeyError(f"unknown config path {path!r}")
            section = section[key]
        if not isinstance(section, dict) or leaf not in section:
            raise KeyError(f"unknown config path {path!r}")  # catch typos before running
        section[leaf] = value
    return SimulationConfig.model_validate(raw)


def run_dir_for(root: Path, condition: Condition, seed: int) -> Path:
    return root / f"{condition.label}-s{seed}"


def run_condition(
    base: SimulationConfig,
    condition: Condition,
    seeds: Iterable[int],
    root: Path,
    experiment_id: str,
) -> list[Path]:
    """Run one condition for every seed. Re-running overwrites (results are deterministic)."""
    dirs = []
    for seed in seeds:
        config = apply_changes(base, {**condition.changes, "run.seed": seed})
        out = run_dir_for(root, condition, seed)
        execute_run(
            config, out, experiment_id=experiment_id, condition=condition.label, overwrite=True
        )
        dirs.append(out)
    return dirs


def settled_gene_means(run_dir: Path, first_tick: int, last_tick: int) -> dict[str, float] | None:
    """Each gene's population mean, averaged over ticks ``first_tick..last_tick`` inclusive.

    Averaging over a window smooths tick-to-tick noise. Returns None if the run didn't reach
    ``last_tick`` with organisms alive (extinction): such runs can't be measured and must be
    reported, not silently dropped.
    """
    meta = json.loads((run_dir / "run.json").read_text())
    if meta["status"] != "completed" or meta["ticks_run"] <= last_tick:
        return None
    # With sampling (ticks_every > 1) only every n-th tick has a row, plus the final tick.
    every = meta.get("ticks_every", 1)
    final = meta["ticks_run"] - 1
    recorded = [t for t in range(first_tick, last_tick + 1) if t % every == 0 or t == final]
    by_gene: dict[str, list[float]] = {}
    with (run_dir / "gene_stats.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            if first_tick <= int(row["tick"]) <= last_tick and int(row["n"]) > 0:
                by_gene.setdefault(row["gene"], []).append(float(row["mean"]))
    if not by_gene or any(len(v) != len(recorded) for v in by_gene.values()):
        return None  # the population was empty for part of the window
    return {gene: statistics.fmean(values) for gene, values in by_gene.items()}


def genomes_never_changed(run_dir: Path) -> bool:
    """True if every recorded genome equals the founders' (no mutation took effect)."""
    meta = json.loads((run_dir / "run.json").read_text())
    initial = {g: spec["initial"] for g, spec in meta["config"]["genome"].items()}
    with (run_dir / "organisms.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            if any(float(row[f"gene_{g}"]) != v for g, v in initial.items()):
                return False
    return meta.get("mutations", 0) == 0


def paired(a: dict[int, float | None], b: dict[int, float | None]) -> tuple[list[float], list[int]]:
    """Per-seed differences a - b, and the seeds dropped because either side is missing."""
    diffs, dropped = [], []
    for seed in sorted(a):
        if a[seed] is None or b.get(seed) is None:
            dropped.append(seed)
        else:
            diffs.append(a[seed] - b[seed])
    return diffs, dropped

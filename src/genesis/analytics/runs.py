"""Executing one run end to end: simulate, and record everything to an output directory.

The CLI calls this, and later the API (Milestone 5) and batch experiments (Milestone 3) will
too, so it holds the logic and the CLI stays a thin wrapper.

Output directory layout:

    run.json        provenance and status (written first, updated at the end)
    ticks.csv       one row per tick (TickSummary)
    gene_stats.csv  one row per (tick, gene): n, mean, sd, min, max of the living population
    genomes.csv     every living genome, every recording.genome_snapshot_every ticks + final
    organisms.csv   one row per organism that ever lived (genes and traits)
    mutations.csv   one row per gene change at a birth (header only when mutation is off)

Retention policy (spec section 9): every tick, every organism and every mutation is recorded;
full genomes are sampled (default every 50 ticks). Measured for a 20,000-tick evolution run
(seed 42): gene_stats.csv 10 MB (120,000 rows), genomes.csv 3.8 MB, all files ~16 MB.
Other per-event logs (each meal, each death) are not recorded.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from genesis.analytics.metrics import (
    MUTATION_FIELDS,
    ORGANISM_FIELDS,
    TICK_FIELDS,
    mutation_rows,
    organism_rows,
)
from genesis.analytics.provenance import environment, git_info
from genesis.analytics.recorder import GENE_STAT_FIELDS, GENOME_SNAPSHOT_FIELDS, RunRecorder
from genesis.analytics.storage import write_csv, write_json
from genesis.core.config import SimulationConfig
from genesis.core.simulation import Simulation, TickSummary

RUN_FILE, TICKS_FILE, ORGANISMS_FILE = "run.json", "ticks.csv", "organisms.csv"
MUTATIONS_FILE = "mutations.csv"
GENE_STATS_FILE, GENOMES_FILE = "gene_stats.csv", "genomes.csv"

# run.json fields that legitimately differ between two otherwise identical runs.
VOLATILE_FIELDS = {"run_id", "started_at", "finished_at", "duration_seconds"}


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    out_dir: Path
    ticks_run: int
    stop_reason: str
    final_population: int
    final_state_digest: str


def new_run_id(seed: int) -> str:
    """A unique, human-readable run ID, e.g. ``20261018T235501Z-s42-a1b2c3``.

    The random suffix comes from the operating system (uuid4), not from the simulation's
    random streams, so creating an ID can never affect results.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-s{seed}-{uuid.uuid4().hex[:6]}"


def execute_run(
    config: SimulationConfig,
    out_dir: Path,
    *,
    run_id: str | None = None,
    experiment_id: str | None = None,
    overwrite: bool = False,
    on_tick: Callable[[TickSummary], None] | None = None,
) -> RunResult:
    """Run one simulation and write its output files to ``out_dir``.

    ``run.json`` is written with status "running" *before* simulating, then rewritten as
    "completed" or "failed". A crashed run therefore leaves an honest record of what was
    attempted, rather than nothing.

    Raises FileExistsError if ``out_dir`` already holds files and ``overwrite`` is False:
    silently replacing an earlier run's results is a way to lose data.
    """
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"{out_dir} is not empty; choose another --out or use --overwrite")
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or new_run_id(config.run.seed)
    meta: dict = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": "running",
        "started_at": _now(),
        "seed": config.run.seed,
        "config": config.model_dump(mode="json"),
        "git": git_info(),
        "environment": environment(),
    }
    run_path = out_dir / RUN_FILE
    write_json(run_path, meta)

    started = time.perf_counter()
    sim = Simulation(config)
    recorder = RunRecorder(config.recording.genome_snapshot_every)
    try:
        while not sim.finished:
            summary = sim.step()
            recorder.observe(sim, summary)
            if on_tick is not None:
                on_tick(summary)
    except Exception as exc:
        meta.update(
            status="failed",
            finished_at=_now(),
            duration_seconds=round(time.perf_counter() - started, 3),
            failed_at_tick=sim.tick,
            error=f"{type(exc).__name__}: {exc}",
        )
        write_json(run_path, meta)
        raise

    write_csv(out_dir / TICKS_FILE, TICK_FIELDS, recorder.ticks)
    write_csv(out_dir / GENE_STATS_FILE, GENE_STAT_FIELDS, recorder.gene_stats)
    write_csv(out_dir / GENOMES_FILE, GENOME_SNAPSHOT_FIELDS, recorder.genomes)
    write_csv(out_dir / ORGANISMS_FILE, ORGANISM_FIELDS, organism_rows(sim))
    write_csv(out_dir / MUTATIONS_FILE, MUTATION_FIELDS, mutation_rows(sim))

    stop_reason = "extinction" if not sim.organisms else "max_ticks"
    digest = sim.state_digest()
    meta.update(
        status="completed",
        finished_at=_now(),
        duration_seconds=round(time.perf_counter() - started, 3),
        ticks_run=len(recorder.ticks),
        stop_reason=stop_reason,
        final_population=len(sim.organisms),
        organisms_ever=len(sim.organisms) + len(sim.dead),
        mutations=len(sim.mutation_log),
        final_state_digest=digest,
    )
    write_json(run_path, meta)
    ticks_run = len(recorder.ticks)
    return RunResult(run_id, out_dir, ticks_run, stop_reason, len(sim.organisms), digest)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

"""RunRecorder: decides what to keep from each tick of a run.

The simulation knows nothing about files or sampling intervals; the recorder watches it after
every tick and collects rows. That keeps recording policy (what, how often) out of the
simulation core.

Collected per run:

    ticks        one TickSummary row per tick
    gene_stats   one row per (tick, gene): n, mean, sd, min, max over the living population
    genomes      every living organism's genes, every ``genome_snapshot_every`` ticks and on
                 the final tick

gene_stats uses "tidy" (long) format: one observation per row, with the gene name as a column
value rather than baked into column names. Analysis tools (pandas, DuckDB, Plotly) can then
filter, group and plot any gene the same way.
"""

from __future__ import annotations

import math

import numpy as np

from genesis.analytics.metrics import GENE_FIELDS, tick_row
from genesis.core.simulation import Simulation, TickSummary
from genesis.evolution.genome import gene_names

GENE_STAT_FIELDS: list[str] = ["tick", "gene", "n", "mean", "sd", "min", "max"]
# The same gene_* column names as organisms.csv, so the two files can be joined on them.
GENOME_SNAPSHOT_FIELDS: list[str] = ["tick", "id", *GENE_FIELDS]


def gene_stat_rows(tick: int, genome_values: dict[str, list[float]]) -> list[dict]:
    """Summary statistics per gene for one set of organisms.

    ``sd`` is the *population* standard deviation (dividing by n, NumPy's default ddof=0):
    these numbers describe exactly the organisms alive, not an estimate of some larger group.
    An empty population gets n = 0 and NaN statistics ("no value", not zero).
    """
    rows = []
    for gene, values in genome_values.items():
        if values:
            v = np.asarray(values, dtype=np.float64)
            stats = (float(v.mean()), float(v.std()), float(v.min()), float(v.max()))
        else:
            stats = (math.nan,) * 4
        rows.append(dict(zip(GENE_STAT_FIELDS, (tick, gene, len(values), *stats), strict=True)))
    return rows


class RunRecorder:
    def __init__(self, genome_snapshot_every: int):
        if genome_snapshot_every < 1:
            raise ValueError("genome_snapshot_every must be at least 1")
        self.genome_snapshot_every = genome_snapshot_every
        self.ticks: list[dict] = []
        self.gene_stats: list[dict] = []
        self.genomes: list[dict] = []

    def observe(self, sim: Simulation, summary: TickSummary) -> None:
        """Call once after every ``sim.step()``. Reads the simulation; never changes it."""
        tick = summary.tick
        self.ticks.append(tick_row(summary))

        living = sim.organisms
        by_gene = {g: [getattr(o.genome, g) for o in living] for g in gene_names()}
        self.gene_stats.extend(gene_stat_rows(tick, by_gene))

        # Snapshot on the interval, and always on the final tick so the end state is kept.
        if tick % self.genome_snapshot_every == 0 or sim.finished:
            for org in living:
                genes = {f"gene_{g}": v for g, v in org.genome.as_dict().items()}
                self.genomes.append({"tick": tick, "id": org.id, **genes})

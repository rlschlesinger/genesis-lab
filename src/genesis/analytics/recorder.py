"""RunRecorder: decides what to keep from each tick of a run.

The simulation knows nothing about files or sampling intervals; the recorder watches it after
every tick and collects rows. That keeps recording policy (what, how often) out of the
simulation core.

Collected per run:

    ticks        one TickSummary row per tick
    gene_stats   one row per (tick, gene): n, mean, sd, min, max over the living population
    genomes      every living organism's genes, every ``genome_snapshot_every`` ticks and on
                 the final tick
    events       optional log of births, deaths and meals (``recording.events``)

With ``ticks_every`` > 1, ticks and gene_stats keep every n-th tick (plus the final one).

gene_stats uses "tidy" (long) format: one observation per row, with the gene name as a column
value rather than baked into column names. Analysis tools (pandas, DuckDB, Plotly) can then
filter, group and plot any gene the same way.
"""

from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np

from genesis.analytics.metrics import GENE_FIELDS, tick_row
from genesis.core.simulation import Simulation, TickSummary
from genesis.evolution.genome import gene_names

GENE_STAT_FIELDS: list[str] = ["tick", "gene", "n", "mean", "sd", "min", "max"]
EVENT_FIELDS: list[str] = ["tick", "seq", "kind", "organism_id", "other_id", "energy", "x", "y",
                           "detail"]  # fmt: skip
# TickSummary columns that count things happening *during* a tick (flows, not stocks).
FLOW_FIELDS: tuple[str, ...] = ("births", "deaths", "food_spawned", "food_eaten", "mutations")
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
    def __init__(
        self,
        genome_snapshot_every: int,
        ticks_every: int = 1,
        events: tuple[str, ...] = (),
    ):
        if genome_snapshot_every < 1 or ticks_every < 1:
            raise ValueError("recording intervals must be at least 1")
        self.genome_snapshot_every = genome_snapshot_every
        self.ticks_every = ticks_every
        self.event_kinds = frozenset(events)
        self.ticks: list[dict] = []
        self.gene_stats: list[dict] = []
        self.genomes: list[dict] = []
        self.events: list[dict] = []
        # Flow columns accumulated since the last recorded tick row.
        self._pending = dict.fromkeys(FLOW_FIELDS, 0)

    def observe(self, sim: Simulation, summary: TickSummary) -> None:
        """Call once after every ``sim.step()``. Reads the simulation; never changes it."""
        tick = summary.tick
        self._record_events(sim)

        # Flows (things that happened during a tick) are summed between recorded rows, so a
        # sampled ticks.csv still gives true totals. Stocks (population, food count, mean
        # energy, lineages) are a snapshot of the recorded tick itself.
        row = tick_row(summary)
        for field in FLOW_FIELDS:
            self._pending[field] += row[field]
        if tick % self.ticks_every != 0 and not sim.finished:
            return
        self.ticks.append(row | self._pending)
        self._pending = dict.fromkeys(FLOW_FIELDS, 0)

        living = sim.organisms
        by_gene = {g: [getattr(o.genome, g) for o in living] for g in gene_names()}
        self.gene_stats.extend(gene_stat_rows(tick, by_gene))

        # Snapshot on the interval, and always on the final tick so the end state is kept.
        if tick % self.genome_snapshot_every == 0 or sim.finished:
            for org in living:
                genes = {f"gene_{g}": v for g, v in org.genome.as_dict().items()}
                self.genomes.append({"tick": tick, "id": org.id, **genes})

    def _record_events(self, sim: Simulation) -> None:
        if not self.event_kinds:
            return
        kept = [e for e in sim.events_this_tick if e.kind in self.event_kinds]
        for seq, event in enumerate(kept):
            row = asdict(event)
            self.events.append({"seq": seq, **row})
